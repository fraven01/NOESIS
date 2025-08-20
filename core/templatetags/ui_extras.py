from django import template

register = template.Library()

BTN_VARIANTS = {

    "primary": "bg-primary text-background dark:text-text-light hover:bg-primary-dark",
    "secondary": "border border-primary text-primary bg-transparent hover:bg-primary-light",

    "success": "bg-success text-text dark:text-text-light hover:bg-success-dark",
    "danger": "bg-error text-text dark:text-text-light hover:bg-error-dark",
    "danger-light": "bg-error-light text-error-dark dark:text-error-dark hover:bg-error-lighter",
    "muted": "bg-background text-text dark:text-text-light hover:bg-background-dark",
    "disabled": "bg-background text-text dark:text-text-light cursor-not-allowed",
}

@register.simple_tag
def btn_classes(variant: str = "primary") -> str:
    """Gibt die Tailwind-Klassen f\u00fcr die Button-Variante zur\u00fcck."""
    return BTN_VARIANTS.get(variant, BTN_VARIANTS["primary"])
