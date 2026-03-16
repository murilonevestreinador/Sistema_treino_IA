TRILAB_DEFAULT_THEME = {
    "cor_primaria": "#1b6f5c",
    "cor_secundaria": "#2f8f7a",
    "cor_botao": "#1b6f5c",
    "cor_cards": "#f7fbf9",
    "cor_header": "#102f2b",
    "logo_url": None,
}


def normalizar_hex(hex_color, fallback="#1b6f5c"):
    valor = str(hex_color or fallback or "").strip()
    if not valor:
        return fallback.lower()
    if not valor.startswith("#"):
        valor = f"#{valor}"
    if len(valor) == 4:
        valor = "#" + "".join(caractere * 2 for caractere in valor[1:])
    if len(valor) != 7:
        return str(fallback).lower()
    try:
        int(valor[1:], 16)
    except ValueError:
        return str(fallback).lower()
    return valor.lower()


def hex_to_rgb(hex_color):
    cor = normalizar_hex(hex_color, "#000000")
    return tuple(int(cor[indice:indice + 2], 16) for indice in (1, 3, 5))


def rgb_to_hex(rgb):
    canais = [max(0, min(255, int(round(valor)))) for valor in rgb]
    return "#{:02x}{:02x}{:02x}".format(*canais)


def calcular_luminancia(hex_color):
    def _canal_linear(valor):
        valor = valor / 255
        if valor <= 0.03928:
            return valor / 12.92
        return ((valor + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(hex_color)
    return 0.2126 * _canal_linear(r) + 0.7152 * _canal_linear(g) + 0.0722 * _canal_linear(b)


def cor_eh_escura(hex_color):
    return calcular_luminancia(hex_color) < 0.38


def razao_contraste(hex_color_a, hex_color_b):
    luminancia_a = calcular_luminancia(hex_color_a)
    luminancia_b = calcular_luminancia(hex_color_b)
    mais_clara = max(luminancia_a, luminancia_b)
    mais_escura = min(luminancia_a, luminancia_b)
    return (mais_clara + 0.05) / (mais_escura + 0.05)


def cor_texto_contraste(hex_color):
    candidatos = ("#ffffff", "#111111", "#222222")
    melhor = max(candidatos, key=lambda cor: razao_contraste(hex_color, cor))
    return melhor


def misturar_cores(hex_color_base, hex_color_alvo, proporcao):
    base = hex_to_rgb(hex_color_base)
    alvo = hex_to_rgb(hex_color_alvo)
    proporcao = max(0.0, min(1.0, float(proporcao)))
    return rgb_to_hex(
        tuple(base[indice] + (alvo[indice] - base[indice]) * proporcao for indice in range(3))
    )


def ajustar_tom(hex_color, fator):
    if fator == 0:
        return normalizar_hex(hex_color)
    alvo = "#000000" if fator < 0 else "#ffffff"
    return misturar_cores(hex_color, alvo, abs(float(fator)))


def gerar_paleta_tema(
    cor_primaria,
    cor_secundaria,
    cor_botao=None,
    cor_cards=None,
    cor_header=None,
):
    primary = normalizar_hex(cor_primaria, TRILAB_DEFAULT_THEME["cor_primaria"])
    secondary = normalizar_hex(cor_secundaria, TRILAB_DEFAULT_THEME["cor_secundaria"])
    button_base = normalizar_hex(cor_botao or primary, primary)
    header_base = normalizar_hex(cor_header or ajustar_tom(primary, -0.58), TRILAB_DEFAULT_THEME["cor_header"])
    card_base = normalizar_hex(cor_cards or ajustar_tom(primary, 0.95), TRILAB_DEFAULT_THEME["cor_cards"])

    primary_dark = ajustar_tom(primary, -0.22)
    primary_darker = ajustar_tom(primary, -0.38)
    primary_light = ajustar_tom(primary, 0.82)
    primary_soft = ajustar_tom(primary, 0.92)

    secondary_dark = ajustar_tom(secondary, -0.18)
    secondary_darker = ajustar_tom(secondary, -0.34)
    secondary_light = ajustar_tom(secondary, 0.80)
    secondary_soft = ajustar_tom(secondary, 0.90)

    background_base = misturar_cores(primary_soft, "#ffffff", 0.55)
    background_soft = misturar_cores(primary_soft, secondary_soft, 0.18)
    background_muted = misturar_cores(primary_soft, "#ffffff", 0.25)
    surface = "#ffffff"
    surface_alt = misturar_cores(primary_soft, "#ffffff", 0.18)
    border_color = misturar_cores(primary, "#ffffff", 0.78)
    border_strong = misturar_cores(primary, "#ffffff", 0.62)

    button_active_bg = ajustar_tom(button_base, -0.14 if not cor_eh_escura(button_base) else -0.04)
    if not cor_eh_escura(button_active_bg):
        button_active_bg = ajustar_tom(button_active_bg, -0.16)
    button_active_text = cor_texto_contraste(button_active_bg)

    button_inactive_bg = misturar_cores(button_base, "#ffffff", 0.90)
    button_inactive_bg_hover = misturar_cores(button_base, "#ffffff", 0.84)
    button_inactive_text = cor_texto_contraste(button_inactive_bg)

    text_default = "#111827"
    text_strong = "#0f172a"
    text_muted = misturar_cores(primary_darker, "#ffffff", 0.62)
    text_on_primary = cor_texto_contraste(primary)
    text_on_secondary = cor_texto_contraste(secondary)
    text_on_header = cor_texto_contraste(header_base)

    success_base = "#15803d"
    warning_base = "#b45309"
    danger_base = "#b91c1c"
    info_base = primary_dark

    success_bg = misturar_cores(success_base, "#ffffff", 0.88)
    warning_bg = misturar_cores(warning_base, "#ffffff", 0.88)
    danger_bg = misturar_cores(danger_base, "#ffffff", 0.90)
    info_bg = misturar_cores(info_base, "#ffffff", 0.88)

    return {
        "primary": primary,
        "primary_dark": primary_dark,
        "primary_darker": primary_darker,
        "primary_light": primary_light,
        "primary_soft": primary_soft,
        "secondary": secondary,
        "secondary_dark": secondary_dark,
        "secondary_darker": secondary_darker,
        "secondary_light": secondary_light,
        "secondary_soft": secondary_soft,
        "button_base": button_base,
        "button_active_bg": button_active_bg,
        "button_active_bg_hover": ajustar_tom(button_active_bg, -0.08),
        "button_active_text": button_active_text,
        "button_inactive_bg": button_inactive_bg,
        "button_inactive_bg_hover": button_inactive_bg_hover,
        "button_inactive_text": button_inactive_text,
        "background_base": background_base,
        "background_soft": background_soft,
        "background_muted": background_muted,
        "surface": surface,
        "surface_alt": surface_alt,
        "card_bg": card_base,
        "card_highlight_bg": misturar_cores(primary, secondary, 0.34),
        "border_color": border_color,
        "border_strong": border_strong,
        "header_bg": header_base,
        "header_gradient_start": ajustar_tom(header_base, -0.10),
        "header_gradient_end": misturar_cores(primary, secondary, 0.52),
        "text_default": text_default,
        "text_strong": text_strong,
        "text_muted": text_muted,
        "text_on_primary": text_on_primary,
        "text_on_secondary": text_on_secondary,
        "text_on_header": text_on_header,
        "focus_ring": misturar_cores(primary, "#ffffff", 0.68),
        "success": success_base,
        "success_bg": success_bg,
        "success_border": misturar_cores(success_base, "#ffffff", 0.68),
        "success_text": cor_texto_contraste(success_bg),
        "warning": warning_base,
        "warning_bg": warning_bg,
        "warning_border": misturar_cores(warning_base, "#ffffff", 0.68),
        "warning_text": cor_texto_contraste(warning_bg),
        "danger": danger_base,
        "danger_bg": danger_bg,
        "danger_border": misturar_cores(danger_base, "#ffffff", 0.68),
        "danger_text": cor_texto_contraste(danger_bg),
        "info": info_base,
        "info_bg": info_bg,
        "info_border": misturar_cores(info_base, "#ffffff", 0.68),
        "info_text": cor_texto_contraste(info_bg),
        "shadow_soft": "0 12px 28px rgba(15, 23, 42, 0.06)",
        "shadow_card": "0 18px 40px rgba(15, 23, 42, 0.08)",
        "shadow_strong": "0 24px 56px rgba(15, 23, 42, 0.12)",
    }
