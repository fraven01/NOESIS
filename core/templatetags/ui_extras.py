from django import template

register = template.Library()

BTN_VARIANTS = {
    "primary": "bg-primary text-white hover:bg-primary-dark",
    "secondary": "bg-gray-300 text-black hover:bg-gray-400",
    "success": "bg-green-600 text-white hover:bg-green-700",
    "danger": "bg-red-600 text-white hover:bg-red-700",
    "danger-light": "bg-red-100 hover:bg-red-200 text-red-700",
    "purple": "bg-purple-600 text-white hover:bg-purple-700",
    "muted": "bg-gray-200 hover:bg-gray-300 text-gray-800",
    "disabled": "bg-gray-300 text-gray-500 cursor-not-allowed",
    "link": "bg-transparent text-white hover:bg-transparent hover:underline",
}

@register.simple_tag
def btn_classes(variant: str = "primary") -> str:
    """Gibt die Tailwind-Klassen f\u00fcr die Button-Variante zur\u00fcck."""
    return BTN_VARIANTS.get(variant, BTN_VARIANTS["primary"])
