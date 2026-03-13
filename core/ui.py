import base64
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

TEMA_PADRAO = {
    "cor_primaria": "#003B7A",
    "cor_secundaria": "#FF3B30",
    "cor_botao": "#FF3B30",
    "cor_cards": "#FFFFFF",
    "cor_header": "#0F172A",
}

ASSETS_DIR = Path.cwd() / "assets"
ICON_FILES = {
    "favicon_16": ASSETS_DIR / "favicon-16x16.png",
    "favicon_32": ASSETS_DIR / "favicon-32x32.png",
    "favicon_ico": ASSETS_DIR / "favicon.ico",
    "apple_touch_icon": ASSETS_DIR / "apple-touch-icon.png",
    "android_192": ASSETS_DIR / "android-chrome-192x192.png",
    "android_512": ASSETS_DIR / "android-chrome-512x512.png",
}


def aplicar_tema(cor_primaria, cor_secundaria, cor_botao=None, cor_cards=None, cor_header=None):
    cor_primaria = cor_primaria or TEMA_PADRAO["cor_primaria"]
    cor_secundaria = cor_secundaria or TEMA_PADRAO["cor_secundaria"]
    cor_botao = cor_botao or TEMA_PADRAO["cor_botao"]
    cor_cards = cor_cards or TEMA_PADRAO["cor_cards"]
    cor_header = cor_header or TEMA_PADRAO["cor_header"]

    st.markdown(
        f"""
        <style>
        :root {{
            --tri-primary: {cor_primaria};
            --tri-secondary: {cor_secundaria};
            --tri-button: {cor_botao};
            --tri-card: {cor_cards};
            --tri-header: {cor_header};
            --tri-bg: #f7f8fa;
            --tri-surface: #ffffff;
            --tri-surface-soft: #f1f5f9;
            --tri-text: #0f172a;
            --tri-text-soft: #475569;
            --tri-border: rgba(15, 23, 42, 0.10);
            --tri-border-strong: rgba(15, 23, 42, 0.16);
            --tri-success: #15803d;
            --tri-warning: #c2410c;
            --tri-danger: #dc2626;
            --tri-radius-sm: 12px;
            --tri-radius-md: 18px;
            --tri-radius-lg: 24px;
            --tri-shadow-soft: 0 12px 28px rgba(15, 23, 42, 0.06);
            --tri-shadow-card: 0 18px 40px rgba(15, 23, 42, 0.08);
            --tri-shadow-strong: 0 24px 56px rgba(15, 23, 42, 0.12);
            --primary-color: {cor_primaria};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_global_styles():
    st.markdown(
        """
        <style>
        .stApp {
            color: var(--tri-text);
            background:
                radial-gradient(circle at top left, rgba(0, 59, 122, 0.08), transparent 26%),
                radial-gradient(circle at bottom right, rgba(255, 59, 48, 0.08), transparent 22%),
                linear-gradient(180deg, #f7f8fa 0%, #ffffff 54%, #f7f8fa 100%);
        }
        html, body, [class*="css"] {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }
        .main .block-container {
            max-width: 1280px;
            padding-top: 1.35rem;
            padding-bottom: 2.5rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
        }
        h1, h2, h3, h4, h5, h6 {
            color: var(--tri-text);
            letter-spacing: -0.03em;
            font-weight: 800;
        }
        h1 {
            font-size: clamp(2rem, 2.6vw, 2.9rem);
        }
        h2 {
            font-size: clamp(1.45rem, 2vw, 2.05rem);
        }
        p, li, label, .stMarkdown, .stCaption {
            color: var(--tri-text-soft);
        }
        a {
            color: var(--tri-primary);
            text-decoration: none;
        }
        a:hover {
            color: var(--tri-secondary);
        }
        header[data-testid="stHeader"] {
            background: rgba(247, 248, 250, 0.82);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid rgba(15, 23, 42, 0.06);
        }
        [data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, #0f172a 0%, #111827 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] * {
            color: rgba(248, 250, 252, 0.94);
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stFormSubmitButton > button {
            background: rgba(255, 255, 255, 0.06) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            color: #f8fafc !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] .stFormSubmitButton > button:hover {
            background: rgba(255, 255, 255, 0.12) !important;
            border-color: rgba(255, 255, 255, 0.18) !important;
        }
        .stButton > button,
        .stFormSubmitButton > button,
        button[kind="primary"] {
            min-height: 2.95rem;
            border-radius: 999px;
            border: 1px solid transparent !important;
            background: linear-gradient(135deg, var(--tri-button) 0%, var(--tri-secondary) 100%) !important;
            color: #ffffff !important;
            font-weight: 800;
            letter-spacing: 0.01em;
            box-shadow: 0 14px 28px rgba(255, 59, 48, 0.18);
            transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover,
        button[kind="primary"]:hover {
            transform: translateY(-1px);
            filter: brightness(0.98);
            box-shadow: 0 18px 32px rgba(255, 59, 48, 0.22);
            color: #ffffff !important;
        }
        .stButton > button:focus,
        .stFormSubmitButton > button:focus,
        button[kind="primary"]:focus {
            box-shadow: 0 0 0 4px rgba(0, 59, 122, 0.14), 0 18px 32px rgba(255, 59, 48, 0.18) !important;
        }
        button[kind="secondary"] {
            background: #ffffff !important;
            color: var(--tri-text) !important;
            border: 1px solid rgba(15, 23, 42, 0.12) !important;
            box-shadow: none !important;
        }
        button[kind="secondary"]:hover {
            border-color: rgba(0, 59, 122, 0.24) !important;
            color: var(--tri-primary) !important;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stDateInput"] input,
        div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] > div,
        div[data-testid="stSelectbox"] > div {
            border-radius: 16px !important;
            border: 1px solid var(--tri-border) !important;
            background: rgba(255, 255, 255, 0.98) !important;
            color: var(--tri-text) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
        }
        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus,
        div[data-testid="stNumberInput"] input:focus,
        div[data-testid="stDateInput"] input:focus {
            border-color: rgba(0, 59, 122, 0.28) !important;
            box-shadow: 0 0 0 4px rgba(0, 59, 122, 0.10) !important;
        }
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stMultiSelect"] label,
        div[data-testid="stFileUploader"] label {
            color: var(--tri-text) !important;
            font-weight: 700 !important;
        }
        .stCheckbox label,
        .stRadio label {
            color: var(--tri-text) !important;
        }
        div[data-testid="stTabs"] {
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid var(--tri-border);
            border-radius: 22px;
            padding: 0.45rem;
            box-shadow: var(--tri-shadow-soft);
        }
        button[data-baseweb="tab"] {
            border-radius: 999px;
            min-height: 2.65rem;
            font-weight: 700;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: rgba(0, 59, 122, 0.10) !important;
            color: var(--tri-primary) !important;
        }
        div[data-testid="stMetric"] {
            border-radius: 20px;
            border: 1px solid var(--tri-border);
            background: rgba(255, 255, 255, 0.96);
            box-shadow: var(--tri-shadow-soft);
            padding: 1rem 1.05rem;
        }
        div[data-testid="stMetricLabel"] {
            color: var(--tri-text-soft);
        }
        div[data-testid="stMetricValue"] {
            color: var(--tri-text);
            font-weight: 800;
        }
        .stAlert {
            border-radius: 18px;
            border: 1px solid var(--tri-border) !important;
            box-shadow: var(--tri-shadow-soft);
        }
        .stDataFrame, div[data-testid="stDataFrame"] {
            border: 1px solid var(--tri-border);
            border-radius: 20px;
            overflow: hidden;
            background: #ffffff;
            box-shadow: var(--tri-shadow-soft);
        }
        div[data-testid="stForm"] {
            border: 1px solid var(--tri-border);
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.95);
            padding: 1rem;
            box-shadow: var(--tri-shadow-soft);
        }
        [data-testid="stPopover"] > div {
            border-radius: 22px !important;
            border: 1px solid var(--tri-border) !important;
            box-shadow: var(--tri-shadow-card) !important;
        }
        .auth-brand {
            text-align: center;
            margin-bottom: 1.25rem;
        }
        .auth-brand-logo {
            display: block;
            margin: 0 auto;
            height: auto;
        }
        .auth-brand-logo-desktop {
            width: min(620px, 84%);
        }
        .auth-brand-logo-mobile {
            display: none;
            width: min(320px, 72%);
        }
        .auth-brand p {
            margin: 0.55rem auto 0;
            color: var(--tri-text-soft);
            font-size: 1rem;
            max-width: 34rem;
        }
        .auth-card {
            border: 1px solid var(--tri-border);
            border-radius: 26px;
            background: rgba(255, 255, 255, 0.96);
            box-shadow: var(--tri-shadow-strong);
            padding: 1.25rem 1.2rem 1.05rem;
            margin-top: 1rem;
            margin-bottom: 0.8rem;
        }
        .auth-card-header h3 {
            margin: 0;
            color: var(--tri-text);
            font-size: 1.15rem;
        }
        .auth-card-header p {
            margin: 0.3rem 0 0;
            color: var(--tri-text-soft);
            font-size: 0.94rem;
        }
        .app-shell,
        .metric-card,
        .workout-detail,
        .history-card,
        .exercise-card,
        .section-shell,
        .workout-card,
        .trainer-editor-shell,
        .trainer-editor-card {
            background: var(--tri-card) !important;
            border: 1px solid var(--tri-border) !important;
            box-shadow: var(--tri-shadow-soft) !important;
        }
        @media (max-width: 1024px) {
            .main .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
        }
        @media (max-width: 768px) {
            .main .block-container {
                padding-top: 0.9rem;
                padding-bottom: 1.3rem;
                padding-left: 0.85rem;
                padding-right: 0.85rem;
            }
            .auth-brand h1 {
                font-size: 1.9rem;
            }
            .auth-brand p {
                font-size: 0.92rem;
            }
            .auth-brand-logo-desktop {
                display: none;
            }
            .auth-brand-logo-mobile {
                display: block;
                width: min(300px, 78%);
            }
            .auth-card,
            div[data-testid="stForm"],
            div[data-testid="stMetric"] {
                border-radius: 18px;
            }
            .stButton > button,
            .stFormSubmitButton > button {
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _arquivo_para_data_url(caminho):
    if not caminho.exists():
        return None

    mime_types = {
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime = mime_types.get(caminho.suffix.lower(), "application/octet-stream")
    conteudo = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{conteudo}"


def inject_app_icons():
    favicon_16 = _arquivo_para_data_url(ICON_FILES["favicon_16"])
    favicon_32 = _arquivo_para_data_url(ICON_FILES["favicon_32"])
    favicon_ico = _arquivo_para_data_url(ICON_FILES["favicon_ico"])
    apple_touch_icon = _arquivo_para_data_url(ICON_FILES["apple_touch_icon"])
    android_192 = _arquivo_para_data_url(ICON_FILES["android_192"])
    android_512 = _arquivo_para_data_url(ICON_FILES["android_512"])

    if not any([favicon_16, favicon_32, favicon_ico, apple_touch_icon, android_192, android_512]):
        return

    manifest = {
        "name": "TriLab TREINAMENTO",
        "short_name": "TriLab",
        "display": "standalone",
        "theme_color": "#003B7A",
        "background_color": "#FFFFFF",
        "icons": [
            {
                "src": android_192,
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": android_512,
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    manifest_json = json.dumps(manifest)

    components.html(
        f"""
        <script>
        const doc = window.parent.document;
        const head = doc.head;

        function upsertLink(id, rel, href, sizes=null, type=null) {{
            if (!href) return;
            let el = doc.getElementById(id);
            if (!el) {{
                el = doc.createElement('link');
                el.id = id;
                head.appendChild(el);
            }}
            el.rel = rel;
            el.href = href;
            if (sizes) el.sizes = sizes;
            if (type) el.type = type;
        }}

        function upsertMeta(id, name, content) {{
            let el = doc.getElementById(id);
            if (!el) {{
                el = doc.createElement('meta');
                el.id = id;
                el.name = name;
                head.appendChild(el);
            }}
            el.content = content;
        }}

        function upsertStyle(id, cssText) {{
            let el = doc.getElementById(id);
            if (!el) {{
                el = doc.createElement('style');
                el.id = id;
                head.appendChild(el);
            }}
            el.textContent = cssText;
        }}

        upsertLink('trilab-favicon-16', 'icon', {json.dumps(favicon_16)}, '16x16', 'image/png');
        upsertLink('trilab-favicon-32', 'icon', {json.dumps(favicon_32)}, '32x32', 'image/png');
        upsertLink('trilab-favicon-ico', 'shortcut icon', {json.dumps(favicon_ico)}, null, 'image/x-icon');
        upsertLink('trilab-apple-touch', 'apple-touch-icon', {json.dumps(apple_touch_icon)}, '180x180', 'image/png');

        upsertMeta('trilab-theme-color', 'theme-color', '#003B7A');
        upsertMeta('trilab-mobile-web-title', 'apple-mobile-web-app-title', 'TriLab TREINAMENTO');
        upsertMeta('trilab-mobile-capable', 'apple-mobile-web-app-capable', 'yes');
        upsertStyle(
            'trilab-sidebar-nav-uppercase',
            `
            [data-testid="stSidebarNav"] a,
            [data-testid="stSidebarNav"] a span,
            [data-testid="stSidebarNav"] div[data-testid="stSidebarNavItems"] span {{
                text-transform: uppercase !important;
            }}
            `
        );

        const manifestData = {manifest_json};
        const manifestBlob = new Blob([JSON.stringify(manifestData)], {{ type: 'application/manifest+json' }});
        const manifestUrl = URL.createObjectURL(manifestBlob);
        upsertLink('trilab-manifest', 'manifest', manifestUrl, null, 'application/manifest+json');
        </script>
        """,
        height=0,
        width=0,
    )


def auth_card_start(title, subtitle):
    return None


def auth_card_end():
    return None
