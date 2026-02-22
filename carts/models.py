from django.db import models

class Cart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField()
    total_amount = models.BigIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_total(self):
        total = sum(item.subtotal() for item in self.items.all())
        self.total_amount = total
        self.save(update_fields=['total_amount'])

    def __str__(self):
        return f"Cart {self.id}"


class CartItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product_id = models.BigIntegerField()
    variant_id = models.BigIntegerField()
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100)
    price = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'variant_id')

    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.variant_name} x {self.quantity}"


class Order(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField()
    order_number = models.CharField(max_length=20, unique=True)
    status = models.CharField(
        max_length=20,
        default='PENDING',
        choices=[
            ('PENDING', 'Pending'),
            ('PAID', 'Paid'),
            ('SHIPPED', 'Shipped'),
            ('DELIVERED', 'Delivered'),
            ('CANCELLED', 'Cancelled'),
        ],
    )
    total_amount = models.BigIntegerField()
    stripe_session_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_id = models.BigIntegerField()
    variant_id = models.BigIntegerField()
    product_name = models.CharField(max_length=255)
    variant_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100)
    price = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def subtotal(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.variant_name} x {self.quantity}"
