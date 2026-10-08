# Social authentication and missing Facebook email

The server verifies Firebase ID tokens, including revocation, and accepts only
supported providers. A verified Facebook identity may omit `email`. Missing UID,
unsupported providers, invalid email claims, and missing Google/Apple email are
rejected. An absent email is never considered verified.

- `POST /api/v1/auth/social/session`: an unlinked Facebook identity without an
  email returns `profile_completion_required` with `email: ""`. Already linked
  identities authenticate by their verified Firebase UID.
- `POST /api/v1/auth/social/signup`: accepts optional `email` alongside the
  existing profile fields. It is required when the provider supplied no email.
  A provider-supplied address takes precedence. A manually entered address uses
  the existing registration OTP flow; no account or auth tokens are created
  until `/auth/verify-email` succeeds.
- If the chosen address already belongs to a client, signup returns
  `account_link_required`. `POST /auth/social/link` accepts optional `email` when
  absent from the provider and still requires that account's password. There is
  no automatic linking by a manually entered address.
- Repeating signup with a changed manual address reuses the pending identity
  and invalidates any OTP issued to the old address.

- `POST /auth/social/signup` accepts `defer_profile: true` to verify the email
  without collecting names, username, phone, or city before login. The signed
  provider name is retained, the server assigns a unique temporary username,
  and phone stays null. After OTP verification, the user has
  `profile_username_pending: true` and can complete `/auth/client/profile/`
  inside the app, like a Google account. Existing clients omitting this flag
  still use the full-profile signup contract.

Apply migration `accounts.0019_deferred_social_profile` before rolling out the
backend. It adds the pending username flag and makes the pending registration
phone nullable. Deploy both backend and customer app changes.
The Meta app's publishing requirements are separate from this fallback.

Regression checks:

```powershell
.\.venv\Scripts\python.exe manage.py test accounts.test_social_auth --settings=config.test_settings
```
