from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem, Transaction, Delivery

class CartItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()
    # Remove required fields from serializer input
    product_slug = serializers.CharField(write_only=True, required=True)
    variant_id = serializers.IntegerField(write_only=True, required=True)
    quantity = serializers.IntegerField(default=1)

    class Meta:
        model = CartItem
        fields = [
            'id',
            'product_slug',  # frontend sends this
            'variant_id',   # frontend sends this
            'quantity',     # frontend sends this
            'product_id',   # fetched from product service
            'product_name', # fetched from product service
            'variant_name', # fetched from product service
            'sku',          # fetched from product service
            'price',        # fetched from product service
            'subtotal'
        ]
        read_only_fields = ['id', 'product_id', 'product_name', 'variant_name', 'sku', 'price', 'subtotal']

    def get_subtotal(self, obj):
        return obj.subtotal()


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'user_id', 'total_amount', 'is_active', 'items']


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product_id', 'variant_id', 'product_name', 'variant_name',
                  'sku', 'price', 'quantity', 'subtotal']

    def get_subtotal(self, obj):
        return obj.subtotal()


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    delivery = DeliverySerializer(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'user_id', 'order_number', 'status', 'total_amount', 'items', 'transactions', 'delivery']
