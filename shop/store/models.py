from django.db import models
from django.conf import settings

class CustomType(models.Model):
    name = models.CharField(max_length=100)              # e.g. "Flat", "3D", "Other"
    price_cents = models.PositiveIntegerField(default=0) # placeholder/base price
    is_negotiable = models.BooleanField(default=False)   # if True, show "Negotiable" instead of a price
    is_default = models.BooleanField(default=False)      # the one pre-selected for the customer
    sort_order = models.PositiveIntegerField(default=0)  # controls display order
    is_active = models.BooleanField(default=True)
    min_images = models.PositiveIntegerField(default=1)
    max_images = models.PositiveIntegerField(default=3)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name

    @property
    def price_display(self):
        if self.is_negotiable:
            return "Negotiable"
        return f"ZAR {self.price_cents / 100:.2f}"

class Colour(models.Model):
    name = models.CharField(max_length=50)               # e.g. "Red"
    hex_value = models.CharField(max_length=7, default="#000000")  # e.g. "#dc2626"
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name
    
class Product(models.Model):
    PRODUCT_TYPES = [
        ("stock", "Stock item"),
        ("custom", "Custom / special order"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)

    # Price stored in minor units (cents) as an integer — avoids rounding bugs
    # and is international-ready (Section 7 of the plan).
    price_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="ZAR")

    product_type = models.CharField(
        max_length=10, choices=PRODUCT_TYPES, default="stock"
    )
    # Only meaningful for stock items; ignored for custom orders.
    stock_quantity = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_custom_order = models.BooleanField(default=False)  # marks THE pinned custom product
    is_pinned = models.BooleanField(default=False)        # floats it to the top of the list

    def __str__(self):
        return f"{self.name} ({self.get_product_type_display()})"

    @property
    def price_display(self):
        return f"{self.currency} {self.price_cents / 100:.2f}"

    @property
    def is_available(self):
        # Inactive products can never be bought.
        if not self.is_active:
            return False
        # Custom items are made to order, so always "available".
        if self.product_type == "custom":
            return True
        # Stock items need stock on hand.
        return self.stock_quantity > 0


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("in_production", "In production"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="ZAR")
    has_custom_items = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.pk} ({self.get_status_display()})"

    @property
    def total_display(self):
        return f"{self.currency} {self.total_cents / 100:.2f}"



class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    # Snapshot the name & price at purchase time, so later edits to the
    # product don't rewrite past orders.
    product_name = models.CharField(max_length=200)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(default=1)

# --- Custom order request details (blank for normal stock items) ---
    colours = models.ManyToManyField("Colour", blank=True)

    custom_name = models.CharField(max_length=200, blank=True)   # customer's name for their request
    length = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    measurement_unit = models.CharField(max_length=10, blank=True)  # mm, cm, m, in, ft
    colour = models.ForeignKey(
        "Colour", on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_total_cents(self):
        return self.unit_price_cents * self.quantity

    @property
    def unit_price_display(self):
        return f"{self.order.currency} {self.unit_price_cents / 100:.2f}"

    @property
    def line_total_display(self):
        return f"{self.order.currency} {self.line_total_cents / 100:.2f}"
    
    @property
    def size_display(self):
        if self.length and self.width:
            return f"{self.length} × {self.width} {self.measurement_unit}"
        return ""
    
    @property
    def colours_display(self):
        return ", ".join(c.name for c in self.colours.all())
    


class CustomOrderImage(models.Model):
    order_item = models.ForeignKey(OrderItem, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="custom_orders/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.order_item}"
    
