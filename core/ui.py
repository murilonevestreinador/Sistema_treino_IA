import base64
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from core.theme import TRILAB_DEFAULT_THEME, gerar_paleta_tema

TEMA_PADRAO = dict(TRILAB_DEFAULT_THEME)

ASSETS_DIR = Path.cwd() / "assets"
ICON_FILES = {
    "favicon_16": ASSETS_DIR / "favicon-16x16.png",
    "favicon_32": ASSETS_DIR / "favicon-32x32.png",
    "favicon_ico": ASSETS_DIR / "favicon.ico",
    "apple_touch_icon": ASSETS_DIR / "apple-touch-icon.png",
    "android_192": ASSETS_DIR / "android-chrome-192x192.png",
    "android_512": ASSETS_DIR / "android-chrome-512x512.png",
}

def aplicar_tema_global(paleta):
    st.markdown(
        f"""
        <style>
        :root {{
            --tri-primary: {paleta["primary"]};
            --tri-primary-dark: {paleta["primary_dark"]};
            --tri-primary-light: {paleta["primary_light"]};
            --tri-primary-soft: {paleta["primary_soft"]};
            --tri-secondary: {paleta["secondary"]};
            --tri-secondary-dark: {paleta["secondary_dark"]};
            --tri-secondary-light: {paleta["secondary_light"]};
            --tri-secondary-soft: {paleta["secondary_soft"]};
            --tri-button: {paleta["button_base"]};
            --tri-card: {paleta["card_bg"]};
            --tri-card-highlight: {paleta["card_highlight_bg"]};
            --tri-header: {paleta["header_bg"]};
            --tri-header-start: {paleta["header_gradient_start"]};
            --tri-header-end: {paleta["header_gradient_end"]};
            --tri-bg: {paleta["background_base"]};
            --tri-bg-soft: {paleta["background_soft"]};
            --tri-bg-muted: {paleta["background_muted"]};
            --tri-surface: {paleta["surface"]};
            --tri-surface-soft: {paleta["surface_alt"]};
            --tri-text: {paleta["text_default"]};
            --tri-text-strong: {paleta["text_strong"]};
            --tri-text-soft: {paleta["text_muted"]};
            --tri-text-on-primary: {paleta["text_on_primary"]};
            --tri-text-on-secondary: {paleta["text_on_secondary"]};
            --tri-text-on-header: {paleta["text_on_header"]};
            --tri-border: {paleta["border_color"]};
            --tri-border-strong: {paleta["border_strong"]};
            --tri-focus-ring: {paleta["focus_ring"]};
            --tri-success: {paleta["success"]};
            --tri-success-bg: {paleta["success_bg"]};
            --tri-success-border: {paleta["success_border"]};
            --tri-success-text: {paleta["success_text"]};
            --tri-warning: {paleta["warning"]};
            --tri-warning-bg: {paleta["warning_bg"]};
            --tri-warning-border: {paleta["warning_border"]};
            --tri-warning-text: {paleta["warning_text"]};
            --tri-danger: {paleta["danger"]};
            --tri-danger-bg: {paleta["danger_bg"]};
            --tri-danger-border: {paleta["danger_border"]};
            --tri-danger-text: {paleta["danger_text"]};
            --tri-info: {paleta["info"]};
            --tri-info-bg: {paleta["info_bg"]};
            --tri-info-border: {paleta["info_border"]};
            --tri-info-text: {paleta["info_text"]};
            --tri-radius-sm: 12px;
            --tri-radius-md: 18px;
            --tri-radius-lg: 24px;
            --tri-shadow-soft: {paleta["shadow_soft"]};
            --tri-shadow-card: {paleta["shadow_card"]};
            --tri-shadow-strong: {paleta["shadow_strong"]};
            --tri-button-active-bg: {paleta["button_active_bg"]};
            --tri-button-active-bg-hover: {paleta["button_active_bg_hover"]};
            --tri-button-active-text: {paleta["button_active_text"]};
            --tri-button-inactive-bg: {paleta["button_inactive_bg"]};
            --tri-button-inactive-bg-hover: {paleta["button_inactive_bg_hover"]};
            --tri-button-inactive-text: {paleta["button_inactive_text"]};
            --tri-button-accent-border: {paleta["border_strong"]};
            --primary-color: {paleta["primary"]};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def aplicar_tema(cor_primaria, cor_secundaria, cor_botao=None, cor_cards=None, cor_header=None):
    paleta = gerar_paleta_tema(
        cor_primaria,
        cor_secundaria,
        cor_botao=cor_botao,
        cor_cards=cor_cards,
        cor_header=cor_header,
    )
    aplicar_tema_global(paleta)
    return paleta


def apply_global_styles():
    aplicar_tema_global(gerar_paleta_tema(TEMA_PADRAO["cor_primaria"], TEMA_PADRAO["cor_secundaria"]))
    st.markdown(
        """
        <style>
        .stApp {
            color: var(--tri-text);
            background:
                radial-gradient(circle at top left, color-mix(in srgb, var(--tri-primary) 16%, transparent), transparent 26%),
                radial-gradient(circle at bottom right, color-mix(in srgb, var(--tri-secondary) 14%, transparent), transparent 22%),
                linear-gradient(180deg, var(--tri-bg) 0%, var(--tri-surface) 54%, var(--tri-bg-soft) 100%);
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
            background: color-mix(in srgb, var(--tri-bg) 82%, white 18%);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--tri-border);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--tri-header-start) 0%, var(--tri-header-end) 100%);
            border-right: 1px solid color-mix(in srgb, var(--tri-text-on-header) 12%, transparent);
        }
        [data-testid="stSidebar"] * {
            color: color-mix(in srgb, var(--tri-text-on-header) 94%, transparent);
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stFormSubmitButton > button {
            background: color-mix(in srgb, var(--tri-text-on-header) 10%, transparent) !important;
            border: 1px solid color-mix(in srgb, var(--tri-text-on-header) 12%, transparent) !important;
            color: var(--tri-text-on-header) !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] button[kind="primary"] {
            background: var(--tri-button-active-bg) !important;
            border: 1px solid transparent !important;
            color: var(--tri-button-active-text) !important;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.22) !important;
        }
        [data-testid="stSidebar"] button[kind="primary"] * {
            color: var(--tri-button-active-text) !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"] {
            background: var(--tri-button-inactive-bg) !important;
            border: 1px solid var(--tri-button-accent-border) !important;
            color: var(--tri-button-inactive-text) !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"] * {
            color: var(--tri-button-inactive-text) !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] .stFormSubmitButton > button:hover {
            background: color-mix(in srgb, var(--tri-text-on-header) 16%, transparent) !important;
            border-color: color-mix(in srgb, var(--tri-text-on-header) 20%, transparent) !important;
        }
        [data-testid="stSidebar"] button[kind="primary"]:hover {
            background: var(--tri-button-active-bg-hover) !important;
            border-color: transparent !important;
        }
        [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background: var(--tri-button-inactive-bg-hover) !important;
            border-color: var(--tri-primary) !important;
        }
        .stButton > button,
        .stFormSubmitButton > button,
        button[kind="primary"] {
            min-height: 2.95rem;
            border-radius: 999px;
            border: 1px solid transparent !important;
            background: var(--tri-button-active-bg) !important;
            color: var(--tri-button-active-text) !important;
            font-weight: 800;
            letter-spacing: 0.01em;
            box-shadow: 0 14px 28px rgba(15, 23, 42, 0.16);
            transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease, background 0.15s ease;
        }
        .stButton > button *,
        .stFormSubmitButton > button *,
        button[kind="primary"] * {
            color: var(--tri-button-active-text) !important;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover,
        button[kind="primary"]:hover {
            transform: translateY(-1px);
            filter: brightness(0.98);
            box-shadow: 0 18px 32px rgba(15, 23, 42, 0.20);
            background: var(--tri-button-active-bg-hover) !important;
            color: var(--tri-button-active-text) !important;
        }
        .stButton > button:focus,
        .stFormSubmitButton > button:focus,
        button[kind="primary"]:focus {
            box-shadow: 0 0 0 4px rgba(0, 59, 122, 0.14), 0 18px 32px rgba(15, 23, 42, 0.18) !important;
        }
        button[kind="secondary"] {
            background: var(--tri-button-inactive-bg) !important;
            color: var(--tri-button-inactive-text) !important;
            border: 1px solid var(--tri-button-accent-border) !important;
            box-shadow: none !important;
        }
        button[kind="secondary"] * {
            color: var(--tri-button-inactive-text) !important;
        }
        button[kind="secondary"]:hover {
            background: var(--tri-button-inactive-bg-hover) !important;
            border-color: var(--tri-primary) !important;
            color: var(--tri-button-inactive-text) !important;
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
            background: color-mix(in srgb, var(--tri-surface) 98%, transparent) !important;
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
            color: var(--tri-button-inactive-text) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            background: var(--tri-button-active-bg) !important;
            color: var(--tri-button-active-text) !important;
            box-shadow: 0 10px 20px rgba(15, 23, 42, 0.14);
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] * {
            color: var(--tri-button-active-text) !important;
        }
        div[data-testid="stMetric"] {
            border-radius: 20px;
            border: 1px solid var(--tri-border);
            background: color-mix(in srgb, var(--tri-surface) 96%, transparent);
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
        [data-baseweb="notification"] {
            border-radius: 18px !important;
        }
        [data-testid="stAlert"][kind="success"],
        [data-baseweb="notification"][kind="positive"] {
            background: var(--tri-success-bg) !important;
            border-color: var(--tri-success-border) !important;
            color: var(--tri-success-text) !important;
        }
        [data-testid="stAlert"][kind="warning"],
        [data-baseweb="notification"][kind="warning"] {
            background: var(--tri-warning-bg) !important;
            border-color: var(--tri-warning-border) !important;
            color: var(--tri-warning-text) !important;
        }
        [data-testid="stAlert"][kind="error"],
        [data-baseweb="notification"][kind="negative"] {
            background: var(--tri-danger-bg) !important;
            border-color: var(--tri-danger-border) !important;
            color: var(--tri-danger-text) !important;
        }
        [data-testid="stAlert"][kind="info"],
        [data-baseweb="notification"][kind="info"] {
            background: var(--tri-info-bg) !important;
            border-color: var(--tri-info-border) !important;
            color: var(--tri-info-text) !important;
        }
        .stDataFrame, div[data-testid="stDataFrame"] {
            border: 1px solid var(--tri-border);
            border-radius: 20px;
            overflow: hidden;
            background: var(--tri-surface);
            box-shadow: var(--tri-shadow-soft);
        }
        div[data-testid="stForm"] {
            border: 1px solid var(--tri-border);
            border-radius: 22px;
            background: color-mix(in srgb, var(--tri-surface) 95%, transparent);
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
            background: color-mix(in srgb, var(--tri-surface) 96%, transparent);
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
        .tri-badge,
        .status-pill {
            border: 1px solid var(--tri-border);
            background: var(--tri-bg-soft);
            color: var(--tri-text) !important;
        }
        .tri-badge--primary {
            background: var(--tri-button-active-bg);
            border-color: var(--tri-button-active-bg);
            color: var(--tri-button-active-text) !important;
        }
        .tri-card-highlight {
            background: linear-gradient(135deg, var(--tri-primary) 0%, var(--tri-secondary) 100%) !important;
            color: var(--tri-text-on-primary) !important;
            border-color: transparent !important;
        }
        .tri-card-highlight * {
            color: inherit !important;
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
        "theme_color": TEMA_PADRAO["cor_primaria"],
        "background_color": TEMA_PADRAO["cor_cards"],
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

        upsertMeta('trilab-theme-color', 'theme-color', {json.dumps(TEMA_PADRAO["cor_primaria"])});
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
