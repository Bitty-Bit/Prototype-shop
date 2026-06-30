from django.contrib import admin
from .models import Product, Order, OrderItem, CustomType, Colour, CustomOrderImage

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "is_custom_order", "is_pinned", "price_display", "stock_quantity", "is_active")
    list_filter = ("product_type", "is_active", "currency", "is_custom_order", "is_pinned")
    search_fields = ("name", "description")

@admin.register(CustomType)
class CustomTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "price_display", "is_negotiable", "is_default", "min_images", "max_images", "sort_order", "is_active")
    list_editable = ("min_images", "max_images", "sort_order", "is_active")
    list_filter = ("is_negotiable", "is_default", "is_active")

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price_cents", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "total_display", "has_custom_items", "created_at")
    list_filter = ("status", "has_custom_items")
    inlines = [OrderItemInline]

@admin.register(Colour)
class ColourAdmin(admin.ModelAdmin):
    list_display = ("name", "hex_value", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")