from markets.region import visible_offer_queryset


def client_offer_catalog(user, *, summary=False):
    """Bulk-load exactly the relations used by the customer serializers."""
    relations = ['service_cities', 'products__market__classification']
    prefixes = ['market', 'products__market']
    if not summary:
        prefixes.append('items__variant__product__market')
    for prefix in prefixes:
        relations.extend(f'{prefix}__{relation}' for relation in
                         ('service_cities', 'delivery_areas', 'market_types', 'subcategory_assignments__subcategory'))
    if not summary:
        for prefix in ('products', 'items__variant__product'):
            relations.extend(f'{prefix}__{relation}' for relation in
                             ('category__classification', 'subcategory', 'subcategories',
                              'attributes__options', 'images', 'variants'))
        relations.extend(f'items__variant__attribute_values__{relation}' for relation in
                         ('attribute', 'option', 'product_attribute', 'product_attribute_option'))
    return (visible_offer_queryset(user).select_related('market__classification')
            .prefetch_related(*relations).order_by('-announcement_priority', '-created_at', '-id'))
