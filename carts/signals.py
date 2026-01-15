from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import CartItem

@receiver(post_save, sender=CartItem)
@receiver(post_delete, sender=CartItem)
def update_cart_total(sender, instance, **kwargs):
    instance.cart.update_total()
