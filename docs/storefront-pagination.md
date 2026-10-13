# Storefront pagination

The existing `GET /api/v1/home/markets/{id}/storefront/` remains compatible.
Pass `include_products=false` to fetch only metadata, subcategories and full-store
metrics, with `products: []`. This skips the product queryset/materialization.

`GET /api/v1/home/markets/{id}/storefront/products/` returns
`{count, next, previous, results}`. It requires an authenticated client and uses
the same active, non-archived, region-visible market rules as storefront details.
Only available, non-archived products with variants are returned.

Query parameters:

- `page`: positive page number, default 1; a page past the end returns 404.
- `page_size`: 1–100, default 30; invalid sizes return 400.
- `subcategory_id`: positive ID; matches primary or many-to-many membership.
- `q`: trimmed search in product name/description or market name.
- `sort`: `name`, `price_asc`, `price_desc`, `newest`. The default is `name`,
  or `newest` when a non-empty search is supplied.

Price ordering uses the minimum variant price before discount. Name and price
ties use ascending product ID; newest uses descending creation time and ID.
Results contain the existing storefront product fields plus compact
`market: {id, name, classification_id}`, so cards retain their market context.
Filtering and ordering occur before pagination; related rows are fetched only
for the page. Empty first pages return 200 with `count: 0` and null navigation.
Live catalog changes do not produce a frozen pagination snapshot; clients dedupe
by product ID and refresh the loaded pages after catalog invalidation.

Deploy the backend before distributing a client that requires this endpoint.
The client must not fall back to downloading the full storefront if the new
endpoint is absent. No schema migration is required.
