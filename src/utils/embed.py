def set_branded_footer(embed, brand_text: str = "Made by Reddington6422"):
    """
    Append branding to an embed's footer while preserving any existing footer text.

    - If the embed already has footer text, append " • {brand_text}".
    - Otherwise, set the footer text to the brand.
    """
    existing = None
    try:
        # discord.Embed footer proxy may have 'text' attribute
        existing = getattr(embed.footer, "text", None)
    except Exception:
        existing = None

    if existing:
        new_text = f"{existing} • {brand_text}"
    else:
        new_text = brand_text

    try:
        embed.set_footer(text=new_text)
    except Exception:
        # Best-effort; ignore if embed cannot set footer
        pass
