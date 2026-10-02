# Consumer contract for this release

Deploy the backend and run its migrations before distributing the new admin
or mobile clients. Existing v1 unpaged response shapes remain available.

## Checkout

Each product row may supply `addition_ids: [integer, ...]`. IDs must be unique,
active, and associated with the selected variant's product. The server adds
their prices to the per-unit price and validates them for preview and create.
Order items return `additions: [{id, name, price}]`; `price` is a decimal string.
Names and prices belong to the saved order and do not change with the catalog.
The idempotency fingerprint includes the selected additions.

Admin creation supports `Idempotency-Key` as well as customer checkout:
201 for the first commit, 200 for the same request replay, 409 for a conflicting
payload. Admin keys are scoped to the administrator and target customer. Use
the same key after a network failure; clear it after confirmed success. Older
clients omitting the header remain compatible.

`delivery_address` retains its original response fields but is backed by the
order's frozen snapshot. Existing orders are backfilled from the current
address at migration time; earlier edits cannot be reconstructed from data
that was never saved. Permanent account deletion erases the frozen copy too.

## Bounded order reads

Admin `orders/?page=1&page_size=25` returns normal pagination, plus:

```json
{
  "metrics": {"total": 20, "assignmentReady": 2, "assigned": 3, "delivered": 15},
  "summary": {"count": 20, "total_value": "2000.00", "total_delivery_fees": "400.00"}
}
```

Filters: `status`, `search` (up to 200 characters), `delivery_type` (`all`,
`fixed_area`, `delivery`), `representative_id`, and `scope` (`active`, `history`,
or omitted for all). Sorting accepts only `-created_at`, `-assigned_at`, or
`-delivered_at`, with an ID tie-breaker. `summary` describes the filtered result
before pagination. `metrics` keeps the order-list behavior of applying status
before search/delivery filters. The opt-in `include_courier_summary=1` adds
global per-courier `{assigned_representative_id, active, delivered, total,
delivered_total}` counts/totals independently of the page and its filters.

Courier `courier/orders/?scope=active|history&page=1&page_size=30` always
paginates and returns `summary: {count, total_value, total_delivery_fees}`.
Optional `delivered_from` and `delivered_before` require timezone-aware ISO
timestamps; the upper bound is exclusive. Unscoped v1 callers remain compatible.
Repeated updates to the same courier order status return the committed order
without overwriting its delivery note/proof or creating another event.

## Account and push changes

Self-service email changes are disabled until proof of ownership of the new
address is implemented; saving the existing address is allowed. All recipient
pushes include `recipient_id`. Consumers validate the recipient and active
session before displaying private content or applying account events. Offline
device unregistration is best effort; deleting the FCM token and filtering
in-app content cannot guarantee suppression of a notification already handed
to the operating system before logout.
