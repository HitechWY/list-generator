import streamlit as st
import pandas as pd
import re
import io
import os
import random
from typing import Tuple, List
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Database setup
Base = declarative_base()

class ProcessingSession(Base):
    __tablename__ = 'processing_sessions'
    
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    total_numbers = Column(Integer, nullable=False)
    valid_numbers = Column(Integer, nullable=False)
    invalid_numbers = Column(Integer, nullable=False)
    success_rate = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CleanedNumber(Base):
    __tablename__ = 'cleaned_numbers'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, nullable=False)
    original_number = Column(String(50), nullable=False)
    cleaned_number = Column(String(15), nullable=False)
    customer_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database connection
@st.cache_resource
def get_database_engine():
    """Get database engine with connection pooling"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        st.error("Database connection not configured")
        return None
    
    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine

def save_processing_session(filename: str, stats: dict):
    """Save processing session to database and return session ID"""
    engine = get_database_engine()
    if not engine:
        return 0
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        processing_session = ProcessingSession(
            filename=filename,
            total_numbers=stats['total_processed'],
            valid_numbers=stats['valid_numbers'],
            invalid_numbers=stats['invalid_numbers'],
            success_rate=f"{stats['valid_percentage']:.1f}%"
        )
        session.add(processing_session)
        session.commit()
        # Get the ID after commit
        session.flush()
        # Access the ID value directly after flush
        try:
            return processing_session.id
        except:
            return 0
    except Exception as e:
        session.rollback()
        st.error(f"Error saving session: {str(e)}")
        return 0
    finally:
        session.close()

def save_cleaned_numbers(session_id: int, cleaned_df: pd.DataFrame, original_numbers: list):
    """Save cleaned numbers to database"""
    engine = get_database_engine()
    if not engine or not session_id:
        return
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        for i, (_, row) in enumerate(cleaned_df.iterrows()):
            cleaned_number = CleanedNumber(
                session_id=session_id,
                original_number=original_numbers[i] if i < len(original_numbers) else "",
                cleaned_number=row['WhatsApp Number'],
                customer_name=row['First Name']
            )
            session.add(cleaned_number)
        session.commit()
    except Exception as e:
        session.rollback()
        st.error(f"Error saving cleaned numbers: {str(e)}")
    finally:
        session.close()

def get_processing_history() -> pd.DataFrame:
    """Get processing history from database"""
    engine = get_database_engine()
    if not engine:
        return pd.DataFrame()
    
    query = """
    SELECT id, filename, total_numbers, valid_numbers, invalid_numbers, 
           success_rate, created_at
    FROM processing_sessions 
    ORDER BY created_at DESC 
    LIMIT 50
    """
    
    try:
        return pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"Error loading history: {str(e)}")
        return pd.DataFrame()

def delete_processing_session(session_id: int) -> bool:
    """Delete a processing session and all its associated cleaned numbers"""
    try:
        engine = get_database_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # First delete all cleaned numbers for this session
        session.execute(text(f"DELETE FROM cleaned_numbers WHERE session_id = {session_id}"))
        
        # Then delete the processing session
        session.execute(text(f"DELETE FROM processing_sessions WHERE id = {session_id}"))
        
        session.commit()
        session.close()
        return True
    except Exception as e:
        st.error(f"Error deleting session: {e}")
        return False

def delete_old_sessions(days_old: int) -> int:
    """Delete processing sessions older than specified days"""
    try:
        engine = get_database_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Delete cleaned numbers first (foreign key constraint)
        delete_numbers_query = f"""
        DELETE FROM cleaned_numbers 
        WHERE session_id IN (
            SELECT id FROM processing_sessions 
            WHERE created_at < NOW() - INTERVAL '{days_old} days'
        )
        """
        
        # Delete old processing sessions
        delete_sessions_query = f"""
        DELETE FROM processing_sessions 
        WHERE created_at < NOW() - INTERVAL '{days_old} days'
        """
        
        # Execute deletions
        numbers_result = session.execute(text(delete_numbers_query))
        sessions_result = session.execute(text(delete_sessions_query))
        
        try:
            deleted_count = sessions_result.rowcount
        except:
            deleted_count = 0
        session.commit()
        session.close()
        
        return deleted_count
    except Exception as e:
        st.error(f"Error deleting old sessions: {e}")
        return 0

def get_database_stats() -> dict:
    """Get database storage statistics"""
    try:
        engine = get_database_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Get total sessions count
        sessions_count = session.execute(text("SELECT COUNT(*) FROM processing_sessions")).scalar()
        
        # Get total cleaned numbers count
        numbers_count = session.execute(text("SELECT COUNT(*) FROM cleaned_numbers")).scalar()
        
        # Get oldest session date
        oldest_session = session.execute(text("SELECT MIN(created_at) FROM processing_sessions")).scalar()
        
        # Get database size (approximate)
        size_query = """
        SELECT 
            pg_size_pretty(pg_total_relation_size('processing_sessions')) as sessions_size,
            pg_size_pretty(pg_total_relation_size('cleaned_numbers')) as numbers_size
        """
        size_result = session.execute(text(size_query)).fetchone()
        
        session.close()
        
        return {
            'total_sessions': sessions_count or 0,
            'total_numbers': numbers_count or 0,
            'oldest_session': oldest_session,
            'sessions_size': size_result[0] if size_result else 'Unknown',
            'numbers_size': size_result[1] if size_result else 'Unknown'
        }
    except Exception as e:
        st.error(f"Error getting database stats: {e}")
        return {
            'total_sessions': 0,
            'total_numbers': 0,
            'oldest_session': None,
            'sessions_size': 'Unknown',
            'numbers_size': 'Unknown'
        }

def validate_uae_phone_number(phone_str: str) -> bool:
    """
    Validate if a phone number meets UAE criteria:
    - Exactly 9 digits (after cleaning and normalization)
    - Starts with valid UAE prefixes: 50, 52, 54, 55, 56, 58
    
    Accepted formats:
    ✅ 501234567 (exactly 9 digits)
    ✅ 0501234567 (leading 0)
    ✅ 971501234567 (international format without +)
    ✅ +971501234567 (international format with +)
    ✅ 50 123 4567 (with spaces)
    ✅ 50-123-4567 (with dashes)
    ✅ 501234567.00 (with decimal points)
    ✅ 0501234567.001255 (with trailing decimal digits)
    """
    # Convert to string and remove any whitespace
    phone_str = str(phone_str).strip()
    
    # Handle decimal points: remove everything after the decimal point
    if '.' in phone_str:
        phone_str = phone_str.split('.')[0]
    
    # Remove any non-digit characters (spaces, dashes, parentheses, plus signs, etc.)
    clean_phone = re.sub(r'[^\d]', '', phone_str)
    
    # Handle different input formats and normalize to 9-digit UAE format:
    
    # 1. International format with country code (+971 or 971)
    if clean_phone.startswith('971') and len(clean_phone) == 12:
        clean_phone = clean_phone[3:]  # Remove 971 prefix
    
    # 2. Local format with leading zero (0501234567)
    elif clean_phone.startswith('0') and len(clean_phone) == 10:
        clean_phone = clean_phone[1:]  # Remove leading 0
    
    # 3. Direct 9-digit format (501234567) - no changes needed
    # This case is handled by the validation below
    
    # Validate the normalized number
    # Must be exactly 9 digits
    if len(clean_phone) != 9 or not clean_phone.isdigit():
        return False
    
    # Must start with valid UAE mobile prefixes
    valid_prefixes = ['50', '52', '54', '55', '56', '58']
    return clean_phone[:2] in valid_prefixes

def convert_to_international_format(phone_str: str) -> str:
    """
    Convert valid UAE phone number to international format by prepending 971
    Uses the same normalization logic as validate_uae_phone_number
    """
    # Clean the phone number first using the same logic as validation
    phone_str = str(phone_str).strip()
    
    # Handle decimal points: remove everything after the decimal point
    if '.' in phone_str:
        phone_str = phone_str.split('.')[0]
    
    # Remove any non-digit characters (spaces, dashes, parentheses, plus signs, etc.)
    clean_phone = re.sub(r'[^\d]', '', phone_str)
    
    # Handle different input formats and normalize to 9-digit UAE format:
    
    # 1. International format with country code (+971 or 971)
    if clean_phone.startswith('971') and len(clean_phone) == 12:
        clean_phone = clean_phone[3:]  # Remove 971 prefix
    
    # 2. Local format with leading zero (0501234567)
    elif clean_phone.startswith('0') and len(clean_phone) == 10:
        clean_phone = clean_phone[1:]  # Remove leading 0
    
    # 3. Direct 9-digit format (501234567) - no changes needed
    
    return f"971{clean_phone}"

def process_phone_numbers(df: pd.DataFrame, phone_column: str, progress_callback=None) -> Tuple[pd.DataFrame, dict]:
    """
    Process the phone numbers from the uploaded file with progress tracking
    Returns processed dataframe and statistics
    """
    # Get the phone column data
    phone_data = df[phone_column].dropna()
    total_count = len(phone_data)
    
    # Check for large file processing
    if total_count > 100000:
        st.warning(f"⚠️ Large file detected ({total_count:,} rows). Processing may take several minutes.")
    
    valid_numbers = []
    invalid_numbers = []
    debug_samples = []
    
    # Process in batches for better memory management
    batch_size = 1000
    processed_count = 0
    
    for batch_start in range(0, total_count, batch_size):
        batch_end = min(batch_start + batch_size, total_count)
        batch_data = phone_data.iloc[batch_start:batch_end]
        
        # Process each phone number in the batch
        for idx, phone in enumerate(batch_data):
            global_idx = batch_start + idx
            phone_str = str(phone).strip()
            
            # Use the original phone string for validation (it handles cleaning internally)
            is_valid = validate_uae_phone_number(phone_str)
            
            if is_valid:
                international_number = convert_to_international_format(phone_str)
                valid_numbers.append(international_number)
            else:
                invalid_numbers.append(phone_str)
            
            # Collect debug samples (first 50 for analysis)
            if global_idx < 50:
                # Get the cleaned version for debugging using same logic as validation
                debug_str = phone_str
                # Handle decimal points: remove everything after the decimal point
                if '.' in debug_str:
                    debug_str = debug_str.split('.')[0]
                clean_debug = re.sub(r'[^\d]', '', debug_str)
                if clean_debug.startswith('971') and len(clean_debug) == 12:
                    clean_debug = clean_debug[3:]
                elif clean_debug.startswith('0') and len(clean_debug) == 10:
                    clean_debug = clean_debug[1:]
                
                debug_samples.append({
                    'original': phone_str,
                    'cleaned': clean_debug,
                    'length': len(clean_debug),
                    'prefix': clean_debug[:2] if len(clean_debug) >= 2 else '',
                    'valid': is_valid
                })
            
            processed_count += 1
            
            # Update progress callback if provided
            if progress_callback and processed_count % 100 == 0:
                progress_percentage = (processed_count / total_count) * 100
                progress_callback.progress(progress_percentage / 100, 
                                         text=f"Processing: {processed_count:,}/{total_count:,} numbers ({progress_percentage:.1f}%)")
    
    # Final progress update
    if progress_callback:
        progress_callback.progress(1.0, text=f"Completed: {total_count:,} numbers processed")
    
    # Create output dataframe with required format
    output_data = []
    for i, number in enumerate(valid_numbers, 1):
        output_data.append({
            'First Name': f'Customer {i}',
            'Last Name': f'Customer {i}',
            'WhatsApp Number': number,
            'Status': '',
            'List Name': '',
            'Tags': '',
            'Created': '',
            'Last Modified': ''
        })
    
    output_df = pd.DataFrame(output_data)
    
    # Statistics with debug info
    stats = {
        'total_processed': total_count,
        'valid_numbers': len(valid_numbers),
        'invalid_numbers': len(invalid_numbers),
        'valid_percentage': (len(valid_numbers) / total_count * 100) if total_count > 0 else 0,
        'debug_samples': debug_samples
    }
    
    return output_df, stats

def detect_phone_column(df: pd.DataFrame) -> str:
    """
    Automatically detect the phone number column
    """
    # Common phone column names
    phone_keywords = ['phone', 'mobile', 'number', 'contact', 'tel', 'cell']
    
    for col in df.columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in phone_keywords):
            return col
    
    # If no keyword match, return the first column
    return str(df.columns[0]) if len(df.columns) > 0 else ""

# Funny Naim Questions for Login
NAIM_QUESTIONS = [
    "Do you like Naim?",
    "Is Naim smarter than Google?",
    "Is Naim better looking than your mirror reflection?",
    "If Naim was a dish, would he be too hot to handle?",
    "Does Naim secretly run the internet?",
    "Can Naim change a lightbulb without touching it?",
    "Would Naim's superhero name be Captain Handsome?",
    "Have you ever dreamed of Naim? Be honest...",
    "Is Naim the reason Wi-Fi works in your house?",
    "Would the world panic if Naim got angry?",
    "Does Naim drink his coffee with charm and confidence?",
    "Would Naim's movie win an Oscar?",
    "Should Naim always skip queues because he's VIP?",
    "Would Earth orbit Naim if he became a planet?",
    "Did you smile just because Naim told you to?",
    "Is Naim the CTO of your heart?",
    "Would you trust Naim with your password?",
    "Does Naim have magical typing powers?",
    "If Naim said 2+2=5, would you agree?",
    "Is Naim the reason you're in a good mood today?",
    "Are Naim's eyes so beautiful they need their own password?",
    "Can Naim be described in one word: 'Legend'?",
    "If Naim ran for president, would you vote for him twice?",
    "Is it true Naim doesn't make typos, just creative remixes?",
    "Would you let Naim name your future child?",
    "Did your day get better just by seeing Naim login?",
    "If Naim was a flavor, would he be legendary spice?",
    "If Naim were a song, should it be on repeat forever?",
    "Is Naim's brain faster than light?",
    "Should Naim be allowed to edit your life decisions?",
    "Would you give Naim your last slice of pizza?",
    "Would you join Naim's fan club as president or secretary?",
    "Is your hairstyle Naim-approved today?",
    "Have you ever heard Naim sneeze? (Yes = Liar, No = Correct)",
    "Has Naim hacked your heart?",
    "Would you faint if Naim winked at you?",
    "Should Naim have his own emoji?",
    "Did Naim invent charisma?",
    "Would Naim's app run faster than time itself?",
    "Could the world handle a clone of Naim?",
    "Is Naim more stable than your internet connection?",
    "Is Naim secretly running this whole website?",
    "Could Naim beat gravity in a dance battle?",
    "Would Naim's perfume smell like success?",
    "Does Naim's brain use quantum logic?",
    "Should Naim be banned from being too cool?",
    "Does the sun shine brighter when someone compliments Naim?",
    "Should every user say yes to Naim... or else?",
    "Is Naim the only reason this system works properly?"
]

def show_login_page():
    """Display the funny login page with JavaScript animations"""
    
    # Add custom CSS for animations and styling
    st.markdown("""
    <style>
    @keyframes bounce {
        0%, 20%, 60%, 100% { transform: translateY(0); }
        40% { transform: translateY(-20px); }
        80% { transform: translateY(-10px); }
    }
    
    @keyframes shake {
        0% { transform: translateX(0); }
        25% { transform: translateX(-5px); }
        50% { transform: translateX(5px); }
        75% { transform: translateX(-5px); }
        100% { transform: translateX(0); }
    }
    
    .bounce-animation {
        animation: bounce 2s infinite;
    }
    
    .shake-animation {
        animation: shake 0.5s ease-in-out;
    }
    
    .login-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 15px;
        margin: 20px 0;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    
    .country-flags {
        font-size: 24px;
        animation: bounce 2s infinite;
        margin: 10px 5px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # JavaScript for country flags animation
    st.markdown("""
    <script>
    function addCountryFlags() {
        const flags = ['🇦🇪', '🇺🇸', '🇬🇧', '🇩🇪', '🇫🇷', '🇮🇹', '🇪🇸', '🇯🇵', '🇰🇷', '🇮🇳'];
        const container = document.createElement('div');
        container.style.textAlign = 'center';
        container.style.margin = '20px 0';
        
        flags.forEach((flag, index) => {
            const span = document.createElement('span');
            span.innerHTML = flag;
            span.className = 'country-flags';
            span.style.animationDelay = (index * 0.2) + 's';
            container.appendChild(span);
        });
        
        return container.outerHTML;
    }
    </script>
    """, unsafe_allow_html=True)
    
    # Login page header with animated countries
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<h1 style="text-align: center; color: white; margin-bottom: 20px;">🔐 ADbuild Secure Login Portal 🔐</h1>', unsafe_allow_html=True)
    
    # Animated country flags
    st.markdown("""
    <div style="text-align: center; margin: 20px 0;">
        <span class="country-flags">🇦🇪</span>
        <span class="country-flags" style="animation-delay: 0.2s;">🇺🇸</span>
        <span class="country-flags" style="animation-delay: 0.4s;">🇬🇧</span>
        <span class="country-flags" style="animation-delay: 0.6s;">🇩🇪</span>
        <span class="country-flags" style="animation-delay: 0.8s;">🇫🇷</span>
        <span class="country-flags" style="animation-delay: 1.0s;">🇮🇹</span>
        <span class="country-flags" style="animation-delay: 1.2s;">🇪🇸</span>
        <span class="country-flags" style="animation-delay: 1.4s;">🇯🇵</span>
        <span class="country-flags" style="animation-delay: 1.6s;">🇰🇷</span>
        <span class="country-flags" style="animation-delay: 1.8s;">🇮🇳</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<p style="text-align: center; color: white; font-size: 18px;">Welcome to the most secure (and fun) WhatsApp list generator in the UAE!</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Login form
    st.markdown("### 🎯 Step 1: Enter Your Credentials")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        username = st.text_input("👤 Username:", placeholder="info@adbuild.ae")
        password = st.text_input("🔑 Password:", type="password", placeholder="Enter your secure password")
        
        if st.button("🚀 Login", type="primary", use_container_width=True):
            if username == "info@adbuild.ae" and password == "Adbuild_934":
                st.session_state.login_step = 2
                st.session_state.current_question = 0
                st.session_state.score = 0
                st.rerun()
            else:
                st.error("❌ Invalid credentials! Try again or face the wrath of Naim!")
                st.markdown('<div class="shake-animation">🚨 Security Alert: Unauthorized access attempt detected! 🚨</div>', unsafe_allow_html=True)

def show_naim_questions():
    """Display the funny Naim questions"""
    
    st.markdown("""
    <div class="login-container">
        <h2 style="text-align: center; color: white;">🎭 Security Verification: The Naim Challenge 🎭</h2>
        <p style="text-align: center; color: white; font-size: 16px;">
            Answer these important security questions to prove you're worthy of accessing our system!
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state if needed
    if 'current_question' not in st.session_state:
        st.session_state.current_question = 0
    if 'score' not in st.session_state:
        st.session_state.score = 0
    
    # Select 5 random questions for this session
    if 'selected_questions' not in st.session_state:
        st.session_state.selected_questions = random.sample(NAIM_QUESTIONS, 5)
    
    current_q = st.session_state.current_question
    
    if current_q < len(st.session_state.selected_questions):
        question = st.session_state.selected_questions[current_q]
        
        st.markdown(f"### Question {current_q + 1} of {len(st.session_state.selected_questions)}")
        st.markdown(f"**{question}**")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("✅ YES", type="primary", use_container_width=True):
                st.session_state.score += 1
                st.success("😊 Excellent answer! 🤗 Naim approves!")
                st.session_state.current_question += 1
                if st.session_state.current_question < len(st.session_state.selected_questions):
                    st.rerun()
                else:
                    st.session_state.login_step = 3
                    st.rerun()
        
        with col2:
            if st.button("❌ NO", use_container_width=True):
                st.error("😠 Wrong answer! You're about to be banned! Try again!")
                st.markdown('<div class="shake-animation">⚠️ Security level decreased! ⚠️</div>', unsafe_allow_html=True)
                st.session_state.current_question += 1
                if st.session_state.current_question < len(st.session_state.selected_questions):
                    st.rerun()
                else:
                    st.session_state.login_step = 3
                    st.rerun()
        
        # Progress bar
        progress = (current_q + 1) / len(st.session_state.selected_questions)
        st.progress(progress, text=f"Security Verification Progress: {current_q + 1}/{len(st.session_state.selected_questions)}")
        
    else:
        show_final_results()

def show_final_results():
    """Show final login results"""
    score = st.session_state.score
    total = len(st.session_state.selected_questions)
    
    if score >= 3:
        st.success(f"🎉 CONGRATULATIONS! You scored {score}/{total}!")
        st.markdown("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); border-radius: 15px; margin: 20px 0;">
            <h2 style="color: white;">🏆 ACCESS GRANTED! 🏆</h2>
            <p style="color: white; font-size: 18px;">You have proven yourself worthy of the ADbuild WhatsApp List Generator!</p>
            <p style="color: white;">Naim is proud of you! 😊🤗</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🚀 Enter the System", type="primary", use_container_width=True):
            st.session_state.authenticated = True
            st.session_state.login_step = 1
            st.rerun()
    else:
        st.error(f"😠 You only scored {score}/{total}. Naim is not impressed!")
        st.markdown("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%); border-radius: 15px; margin: 20px 0;">
            <h2 style="color: white;">🚫 ACCESS DENIED! 🚫</h2>
            <p style="color: white; font-size: 18px;">You have failed the Naim challenge!</p>
            <p style="color: white;">Try again and show more respect to Naim! 😠</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🔄 Try Again", type="secondary", use_container_width=True):
            st.session_state.login_step = 1
            st.session_state.current_question = 0
            st.session_state.score = 0
            if 'selected_questions' in st.session_state:
                del st.session_state.selected_questions
            st.rerun()

def main():
    st.set_page_config(
        page_title="ADbuild WhatsApp List Generator",
        page_icon="📱",
        layout="wide"
    )
    
    # Initialize session state
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'login_step' not in st.session_state:
        st.session_state.login_step = 1
    
    # Check authentication status
    if not st.session_state.authenticated:
        if st.session_state.login_step == 1:
            show_login_page()
            return
        elif st.session_state.login_step == 2:
            show_naim_questions()
            return
        elif st.session_state.login_step == 3:
            show_final_results()
            return
    
    # Show logout button in sidebar
    with st.sidebar:
        st.markdown("### 👤 Session Info")
        st.success("✅ Authenticated as: info@adbuild.ae")
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.session_state.login_step = 1
            if 'selected_questions' in st.session_state:
                del st.session_state.selected_questions
            st.rerun()
    
    # Main application content
    st.title("ADbuild WhatsApp List Generator")
    st.markdown("---")
    
    # Create tabs for different functionalities
    tab1, tab2, tab3, tab4 = st.tabs(["📱 Phone Cleaner", "📊 Processing History", "🗂️ Database Management", "🔧 Debug & Test"])
    
    with tab1:
        st.markdown("""
        ### Welcome to the UAE Phone Number Cleaning Tool
        
        This tool helps you clean and format UAE phone numbers for WhatsApp marketing platforms.
        
        **What it does:**
        - ✅ Validates UAE phone numbers (9 digits, valid prefixes: 50, 52, 54, 55, 56, 58)
        - 🔄 Converts to international format (adds 971 prefix)
        - 📄 Exports in WhatsApp-ready CSV format
        - 🚀 Handles up to 100,000+ phone numbers with progress tracking
        """)
        
        show_phone_cleaner_tab()
    
    with tab2:
        show_processing_history_tab()
    
    with tab3:
        show_database_management_tab()
    
    with tab4:
        show_debug_tab()

def show_database_management_tab():
    """Show database management and cleanup functionality"""
    st.subheader("🗂️ Database Management & Cleanup")
    
    # Get database statistics
    stats = get_database_stats()
    
    # Display current database status
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Sessions", stats['total_sessions'])
    
    with col2:
        st.metric("Total Numbers", f"{stats['total_numbers']:,}")
    
    with col3:
        st.metric("Sessions Size", stats['sessions_size'])
    
    with col4:
        st.metric("Numbers Size", stats['numbers_size'])
    
    if stats['oldest_session']:
        st.info(f"📅 Oldest session: {stats['oldest_session'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    st.markdown("---")
    
    # Cleanup options
    st.subheader("🧹 Cleanup Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ⏰ Delete Old Sessions")
        st.markdown("Remove processing sessions older than specified days to save storage space.")
        
        days_old = st.selectbox(
            "Delete sessions older than:",
            options=[7, 14, 30, 60, 90, 180],
            index=2,
            help="This will permanently delete sessions and all associated phone numbers"
        )
        
        if st.button("🗑️ Delete Old Sessions", type="secondary"):
            with st.spinner("Deleting old sessions..."):
                deleted_count = delete_old_sessions(days_old)
                if deleted_count > 0:
                    st.success(f"✅ Successfully deleted {deleted_count} old sessions!")
                    st.rerun()
                else:
                    st.info("No sessions found older than the specified period.")
    
    with col2:
        st.markdown("### 📋 Individual Session Management")
        st.markdown("View and delete specific processing sessions.")
        
        # Get recent sessions for individual deletion
        history_df = get_processing_history()
        
        if not history_df.empty:
            # Select session to delete
            session_options = []
            for _, row in history_df.head(10).iterrows():
                created = str(row['created_at'])[:16]  # Simple string formatting
                session_options.append(f"{row['filename']} ({created}) - {row['total_numbers']} numbers")
            
            selected_session = st.selectbox(
                "Select session to delete:",
                options=range(len(session_options)),
                format_func=lambda x: session_options[x],
                help="Select a session to permanently delete"
            )
            
            if st.button("🗑️ Delete Selected Session", type="secondary"):
                session_id = history_df.iloc[selected_session]['id']
                with st.spinner("Deleting session..."):
                    if delete_processing_session(session_id):
                        st.success("✅ Session deleted successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete session")
        else:
            st.info("No sessions found in database.")
    
    st.markdown("---")
    
    # Database optimization
    st.subheader("⚡ Database Optimization")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🔧 Maintenance Operations")
        if st.button("🔄 Refresh Database Stats", type="primary"):
            st.rerun()
    
    with col2:
        st.markdown("### ⚠️ Danger Zone")
        st.warning("These operations cannot be undone!")
        
        if st.button("🚨 Clear All Data", type="secondary"):
            st.error("This feature is disabled for safety. Contact administrator if needed.")

def show_processing_history_tab():
    """Show processing history with enhanced details"""
    st.subheader("📊 Processing History")
    
    history_df = get_processing_history()
    
    if not history_df.empty:
        # Summary statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Sessions", len(history_df))
        
        with col2:
            total_processed = history_df['total_numbers'].sum()
            st.metric("Total Numbers Processed", f"{total_processed:,}")
        
        with col3:
            total_valid = history_df['valid_numbers'].sum()
            st.metric("Total Valid Numbers", f"{total_valid:,}")
        
        with col4:
            overall_rate = (total_valid / total_processed * 100) if total_processed > 0 else 0
            st.metric("Overall Success Rate", f"{overall_rate:.1f}%")
        
        st.markdown("---")
        
        # Enhanced history table
        st.markdown("### 📋 Recent Sessions")
        
        # Format the dataframe for better display
        display_df = history_df.copy()
        display_df['created_at'] = display_df['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['total_numbers'] = display_df['total_numbers'].apply(lambda x: f"{x:,}")
        display_df['valid_numbers'] = display_df['valid_numbers'].apply(lambda x: f"{x:,}")
        display_df['invalid_numbers'] = display_df['invalid_numbers'].apply(lambda x: f"{x:,}")
        
        # Rename columns for display
        display_df = display_df.rename(columns={
            'filename': 'File Name',
            'total_numbers': 'Total Numbers',
            'valid_numbers': 'Valid Numbers',
            'invalid_numbers': 'Invalid Numbers',
            'success_rate': 'Success Rate',
            'created_at': 'Processed At'
        })
        
        # Remove ID column from display
        if 'id' in display_df.columns:
            display_df = display_df.drop('id', axis=1)
        
        st.dataframe(display_df, use_container_width=True)
        
        # Download history as CSV
        csv_data = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download History as CSV",
            data=csv_data,
            file_name=f"processing_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No processing history found. Start by processing some phone numbers!")

def show_debug_tab():
    """Show debug and testing functionality"""
    st.subheader("🔧 Debug & Test Tools")
    
    # Phone number testing section
    st.markdown("### 📱 Phone Number Validation Testing")
    
    # Single number test
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Single Number Test:**")
        test_number = st.text_input("Enter a phone number to test:", placeholder="501234567")
        
        if test_number:
            is_valid = validate_uae_phone_number(test_number)
            if is_valid:
                converted = convert_to_international_format(test_number)
                st.success(f"✅ Valid: {test_number} → +{converted}")
            else:
                st.error(f"❌ Invalid: {test_number}")
    
    with col2:
        st.markdown("**Prefix Validation:**")
        valid_prefixes = ["50", "52", "54", "55", "56", "58"]
        
        test_prefix = st.text_input("Test prefix (2 digits):", placeholder="50")
        if test_prefix:
            if len(test_prefix) == 2 and test_prefix.isdigit():
                if test_prefix in valid_prefixes:
                    st.success(f"✅ Prefix '{test_prefix}' is valid")
                else:
                    st.warning(f"❌ Prefix '{test_prefix}' is not valid. Valid prefixes: {', '.join(valid_prefixes)}")
            else:
                st.error("Please enter exactly 2 digits")
    
    st.markdown("---")
    
    # Format testing
    st.markdown("### 🧪 Format Testing")
    
    test_formats = [
        "501234567",
        "0501234567", 
        "971501234567",
        "+971501234567",
        "50 123 4567",
        "50-123-4567",
        "501234567.00",
        "0501234567.001255",
        "971501234567.000",
        "+971501234567.0"
    ]
    
    format_descriptions = [
        "501234567 (9 digits)",
        "0501234567 (with leading 0)",
        "971501234567 (international)",
        "+971501234567 (international with +)",
        "50 123 4567 (with spaces)",
        "50-123-4567 (with dashes)",
        "501234567.00 (with decimal)",
        "0501234567.001255 (with trailing decimals)",
        "971501234567.000 (international with decimal)",
        "+971501234567.0 (international + with decimal)"
    ]
    
    st.markdown("**Live Format Validation:**")
    for i, test_number in enumerate(test_formats):
        is_valid = validate_uae_phone_number(test_number)
        status = "✅" if is_valid else "❌"
        st.text(f"{status} {format_descriptions[i]}")

def show_phone_cleaner_tab():
    """Show the main phone cleaning functionality"""
    
    # File upload section
    st.subheader("📂 Step 1: Upload Your File")
    
    uploaded_file = st.file_uploader(
        "Choose an Excel (.xlsx) or CSV file containing phone numbers",
        type=['xlsx', 'csv'],
        help="Your file should contain a column with phone numbers. Supported formats: Excel (.xlsx) and CSV (.csv)"
    )
    
    if uploaded_file is not None:
        try:
            # Read the file based on type
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
            
            st.success(f"✅ File uploaded successfully! Found {len(df):,} rows and {len(df.columns)} columns.")
            
            # Show file preview
            with st.expander("📋 Preview uploaded data"):
                st.dataframe(df.head(10))
            
            # Column selection
            st.subheader("📋 Step 2: Select Phone Number Column")
            
            # Auto-detect phone column
            detected_column = detect_phone_column(df)
            
            if detected_column:
                st.info(f"🔍 Auto-detected phone column: **{detected_column}**")
            
            # Let user select or confirm the column
            phone_column = st.selectbox(
                "Select the column containing phone numbers:",
                options=df.columns.tolist(),
                index=df.columns.tolist().index(detected_column) if detected_column and detected_column in df.columns else 0
            )
            
            # Show sample data from selected column with validation preview
            st.markdown("**Sample data from selected column:**")
            sample_data = df[phone_column].dropna().head(10).tolist()
            
            # Create validation preview
            valid_count = 0
            for i, sample in enumerate(sample_data, 1):
                is_valid = validate_uae_phone_number(str(sample))
                if is_valid:
                    valid_count += 1
                    st.text(f"{i}. {sample} ✅ Valid")
                else:
                    st.text(f"{i}. {sample} ❌ Invalid")
            
            # Show preview statistics
            total_preview = len(sample_data)
            if total_preview > 0:
                preview_percentage = (valid_count / total_preview) * 100
                st.info(f"📊 Preview: {valid_count}/{total_preview} valid numbers ({preview_percentage:.1f}%) in sample")
            
            # Processing section
            st.subheader("🔄 Step 3: Process Phone Numbers")
            
            if st.button("🚀 Clean Phone Numbers", type="primary"):
                # Ensure phone_column is valid
                if not phone_column or phone_column not in df.columns:
                    st.error("Please select a valid phone number column.")
                    st.stop()
                
                # Show file size information
                total_rows = len(df[phone_column].dropna())
                if total_rows > 50000:
                    st.info(f"📊 Large file detected: {total_rows:,} phone numbers to process")
                    if total_rows > 100000:
                        st.warning("⏱️ Files with 100,000+ numbers may take 5-10 minutes to process")
                
                # Create progress bar
                progress_bar = st.progress(0, text="Initializing...")
                
                try:
                    # Process the phone numbers with progress tracking
                    cleaned_df, stats = process_phone_numbers(df, phone_column, progress_bar)
                    
                    # Clear progress bar
                    progress_bar.empty()
                    
                    # Save to database
                    session_id = save_processing_session(uploaded_file.name, stats)
                    if isinstance(session_id, int) and session_id > 0 and not cleaned_df.empty:
                        # Get original numbers for database storage
                        original_numbers = df[phone_column].dropna().tolist()
                        save_cleaned_numbers(session_id, cleaned_df, original_numbers)
                    
                    # Show statistics
                    st.subheader("📊 Processing Results")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Numbers", f"{stats['total_processed']:,}")
                    
                    with col2:
                        st.metric("Valid Numbers", f"{stats['valid_numbers']:,}")
                    
                    with col3:
                        st.metric("Invalid Numbers", f"{stats['invalid_numbers']:,}")
                    
                    with col4:
                        st.metric("Success Rate", f"{stats['valid_percentage']:.1f}%")
                    
                    # Show debug information if available
                    if 'debug_samples' in stats and stats['debug_samples']:
                        with st.expander("🔍 Debug Analysis - First 50 Numbers"):
                            debug_df = pd.DataFrame(stats['debug_samples'])
                            st.dataframe(debug_df, use_container_width=True)
                            
                            # Show common issues
                            invalid_samples = [s for s in stats['debug_samples'] if not s['valid']]
                            if invalid_samples:
                                st.markdown("**Common Invalid Number Patterns:**")
                                length_issues = [s for s in invalid_samples if s['length'] != 9]
                                prefix_issues = [s for s in invalid_samples if s['length'] == 9 and s['prefix'] not in ['50', '52', '54', '55', '56', '58']]
                                
                                if length_issues:
                                    st.write(f"- {len(length_issues)} numbers with incorrect length")
                                if prefix_issues:
                                    st.write(f"- {len(prefix_issues)} numbers with invalid prefixes")
                    
                    if stats['valid_numbers'] > 0:
                        st.success(f"🎉 Successfully processed {stats['valid_numbers']:,} valid UAE phone numbers!")
                        
                        # Show preview of cleaned data
                        with st.expander("👀 Preview cleaned data"):
                            st.dataframe(cleaned_df.head(10))
                        
                        # Download section
                        st.subheader("📥 Step 4: Download Cleaned File")
                        
                        # Convert dataframe to CSV
                        csv_buffer = io.StringIO()
                        cleaned_df.to_csv(csv_buffer, index=False)
                        csv_data = csv_buffer.getvalue()
                        
                        # Generate filename
                        original_name = uploaded_file.name.rsplit('.', 1)[0]
                        download_filename = f"{original_name}_cleaned_whatsapp.csv"
                        
                        st.download_button(
                            label="📱 Download WhatsApp Ready CSV",
                            data=csv_data,
                            file_name=download_filename,
                            mime="text/csv",
                            type="primary"
                        )
                        
                        st.info("💡 **Tip:** The downloaded file is ready to import into WhatsApp marketing platforms like WA Notifier.")
                        
                    else:
                        st.error("❌ No valid UAE phone numbers found in your file. Please check your data and try again.")
                        
                        st.markdown("""
                        **Valid UAE phone number criteria:**
                        - Must be exactly 9 digits
                        - Must start with: 50, 52, 54, 55, 56, or 58
                        - Examples: 503000654, 521234567, 557890123
                        """)
                
                except Exception as e:
                    progress_bar.empty()
                    st.error(f"❌ Error processing file: {str(e)}")
                    st.markdown("Please check your file format and try again.")
        
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")
            st.markdown("Please ensure your file is a valid Excel (.xlsx) or CSV file.")
    
    else:
        st.info("👆 Please upload a file to get started.")
    
    # Processing History section
    st.markdown("---")
    st.subheader("📊 Processing History")
    
    try:
        history_df = get_processing_history()
        if not history_df.empty:
            # Format the datetime column for better display
            if 'created_at' in history_df.columns:
                history_df['created_at'] = pd.to_datetime(history_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            
            # Rename columns for better display
            display_df = history_df.rename(columns={
                'filename': 'File Name',
                'total_numbers': 'Total Numbers',
                'valid_numbers': 'Valid Numbers', 
                'invalid_numbers': 'Invalid Numbers',
                'success_rate': 'Success Rate',
                'created_at': 'Processed At'
            })
            
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No processing history available yet. Upload and process a file to see your history here.")
    except Exception as e:
        st.warning("Unable to load processing history at this time.")
    
    # Validation Test Section
    st.markdown("---")
    st.subheader("🧪 Phone Number Validation Test")
    
    with st.expander("Test Different Phone Number Formats"):
        st.markdown("**Test your phone number formats before processing:**")
        
        # Test input
        test_number = st.text_input("Enter a phone number to test:", placeholder="e.g., 971501234567, 0501234567, 501234567")
        
        if test_number:
            is_valid = validate_uae_phone_number(test_number)
            if is_valid:
                formatted_number = convert_to_international_format(test_number)
                st.success(f"✅ Valid UAE number: {formatted_number}")
            else:
                st.error(f"❌ Invalid number: {test_number}")
                
                # Show cleaning process for debugging using same logic as validation
                debug_test = test_number
                # Handle decimal points: remove everything after the decimal point
                if '.' in debug_test:
                    debug_test = debug_test.split('.')[0]
                clean_debug = re.sub(r'[^\d]', '', debug_test)
                if clean_debug.startswith('971') and len(clean_debug) == 12:
                    clean_debug = clean_debug[3:]
                elif clean_debug.startswith('0') and len(clean_debug) == 10:
                    clean_debug = clean_debug[1:]
                
                st.info(f"Cleaned version: '{clean_debug}' (Length: {len(clean_debug)})")
                if len(clean_debug) >= 2:
                    prefix = clean_debug[:2]
                    valid_prefixes = ['50', '52', '54', '55', '56', '58']
                    if prefix in valid_prefixes:
                        st.info(f"Prefix '{prefix}' is valid")
                    else:
                        st.warning(f"Prefix '{prefix}' is not valid. Valid prefixes: {', '.join(valid_prefixes)}")
        
        # Show common valid formats with actual validation testing
        st.markdown("**Valid UAE Phone Number Formats (Live Testing):**")
        test_formats = [
            "501234567",
            "0501234567", 
            "971501234567",
            "+971501234567",
            "50 123 4567",
            "50-123-4567",
            "501234567.00",
            "0501234567.001255",
            "971501234567.000",
            "+971501234567.0"
        ]
        
        format_descriptions = [
            "501234567 (9 digits)",
            "0501234567 (with leading 0)",
            "971501234567 (international)",
            "+971501234567 (international with +)",
            "50 123 4567 (with spaces)",
            "50-123-4567 (with dashes)",
            "501234567.00 (with decimal)",
            "0501234567.001255 (with trailing decimals)",
            "971501234567.000 (international with decimal)",
            "+971501234567.0 (international + with decimal)"
        ]
        
        for i, test_number in enumerate(test_formats):
            is_valid = validate_uae_phone_number(test_number)
            status = "✅" if is_valid else "❌"
            st.text(f"{status} {format_descriptions[i]}")
    
    # Instructions section
    st.markdown("---")
    st.subheader("📖 Instructions")
    
    with st.expander("How to use this tool"):
        st.markdown("""
        1. **Prepare your file**: Create an Excel or CSV file with phone numbers in a single column
        2. **Upload**: Use the file uploader above to select your file
        3. **Select column**: Choose which column contains your phone numbers
        4. **Process**: Click the "Clean Phone Numbers" button to validate and convert
        5. **Download**: Get your cleaned file ready for WhatsApp marketing platforms
        
        **Valid UAE Phone Number Format:**
        - Must be exactly 9 digits (after cleaning)
        - Must start with valid prefixes: 50, 52, 54, 55, 56, 58
        - Examples: `503000654`, `521234567`, `557890123`
        - Supports decimal formats: `501234567.00`, `0501234567.001255`
        
        **Output Format:**
        The tool generates a CSV file with these columns:
        - First Name (Customer 1, Customer 2, etc.)
        - Last Name (same as First Name)
        - WhatsApp Number (international format with 971 prefix)
        - Status, List Name, Tags, Created, Last Modified (empty columns for platform compatibility)
        """)
    
    with st.expander("Supported file formats and limits"):
        st.markdown("""
        - **Excel files (.xlsx)**: Standard Excel spreadsheets
        - **CSV files (.csv)**: Comma-separated values files
        - **File size**: Supports 100,000+ rows with progress tracking
        - **Processing**: Batch processing for memory efficiency
        - **Progress**: Real-time progress indicator for large files
        - **Performance**: Optimized for large datasets with automatic memory management
        """)

if __name__ == "__main__":
    main()