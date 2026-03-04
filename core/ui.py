import streamlit as st


def apply_global_styles():
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(23, 112, 104, 0.08), transparent 28%),
                radial-gradient(circle at bottom left, rgba(16, 47, 43, 0.08), transparent 24%),
                linear-gradient(180deg, #f4f7f5 0%, #edf3ef 100%);
        }
        .main .block-container {
            max-width: 420px;
            padding-top: 6vh;
            padding-bottom: 4vh;
        }
        .auth-brand {
            text-align: center;
            margin-bottom: 1rem;
        }
        .auth-brand h1 {
            margin: 0;
            color: #123a34;
            font-size: 2rem;
            line-height: 1.1;
            letter-spacing: -0.02em;
        }
        .auth-brand p {
            margin: 0.45rem 0 0;
            color: #55716b;
            font-size: 0.96rem;
        }
        .auth-card {
            border: 1px solid rgba(18, 58, 52, 0.08);
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 18px 46px rgba(17, 66, 60, 0.10);
            padding: 1.2rem 1.1rem 1rem;
            margin-top: 0.9rem;
            margin-bottom: 0.8rem;
        }
        .auth-card-header h3 {
            margin: 0;
            color: #14342f;
            font-size: 1.1rem;
        }
        .auth-card-header p {
            margin: 0.3rem 0 0;
            color: #5d756f;
            font-size: 0.9rem;
        }
        .auth-card-header {
            margin-bottom: 0.9rem;
        }
        div[data-testid="stTabs"] {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(18, 58, 52, 0.06);
            border-radius: 20px;
            padding: 0.45rem;
        }
        button[data-baseweb="tab"] {
            border-radius: 999px;
            padding-top: 0.35rem;
            padding-bottom: 0.35rem;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stSelectbox"] > div,
        div[data-testid="stRadio"] label,
        div[data-testid="stCheckbox"] label {
            font-size: 0.95rem;
        }
        div[data-testid="stTextInput"] input {
            border-radius: 14px;
            min-height: 2.9rem;
        }
        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: 999px;
            border: none;
            background: linear-gradient(135deg, #1f5c53 0%, #2f7d71 100%);
            color: #ffffff;
            font-weight: 700;
            min-height: 2.9rem;
            width: 100%;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            background: linear-gradient(135deg, #184942 0%, #276a60 100%);
            color: #ffffff;
        }
        header[data-testid="stHeader"] {
            background: transparent;
        }
        @media (max-width: 768px) {
            .main .block-container {
                max-width: 92%;
                padding-top: 1.2rem;
                padding-bottom: 1.2rem;
            }
            .auth-brand h1 {
                font-size: 1.65rem;
            }
            .auth-brand p,
            .auth-card-header p {
                font-size: 0.88rem;
            }
            .auth-card {
                border-radius: 18px;
                padding: 1rem 0.9rem 0.85rem;
            }
            .stButton > button,
            .stFormSubmitButton > button {
                width: 100%;
                min-height: 3rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def auth_card_start(title, subtitle):
    st.markdown(
        f"""
        <div class="auth-card">
            <div class="auth-card-header">
                <h3>{title}</h3>
                <p>{subtitle}</p>
            </div>
        """,
        unsafe_allow_html=True,
    )


def auth_card_end():
    st.markdown("</div>", unsafe_allow_html=True)
