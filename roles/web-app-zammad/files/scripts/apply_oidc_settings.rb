# Idempotently apply Zammad's post-bootstrap fqdn/http_type + OIDC settings.
# The api-bot user creation lives in apply_api_bot.rb so it runs in every
# variant, not just the OIDC ones.
#
# Expects the following ENV vars (set by the calling shell):
#
#   ZAMMAD_FQDN          - public hostname (e.g. helpdesk.infinito.example)
#   ZAMMAD_HTTP_TYPE     - "https" or "http"
#   OIDC_BUTTON_TEXT     - display label for the login button
#   OIDC_CLIENT_ID       - shared Keycloak client id (= SOFTWARE_DOMAIN)
#   OIDC_CLIENT_SECRET   - shared Keycloak client secret
#   OIDC_ISSUER_URL      - Keycloak realm issuer URL

UserInfo.current_user_id = 1

Setting.set("fqdn",      ENV.fetch("ZAMMAD_FQDN"))
Setting.set("http_type", ENV.fetch("ZAMMAD_HTTP_TYPE"))

Setting.set("auth_openid_connect", true)
Setting.set("auth_openid_connect_credentials", {
  "display_name"                 => ENV.fetch("OIDC_BUTTON_TEXT"),
  "identifier"                   => ENV.fetch("OIDC_CLIENT_ID"),
  "secret"                       => ENV.fetch("OIDC_CLIENT_SECRET"),
  "issuer"                       => ENV.fetch("OIDC_ISSUER_URL"),
  "scope"                        => "openid email profile",
  # Match by Keycloak's preferred_username (e.g. "administrator"), NOT by
  # `sub` (UUID). The auto_wizard creates a separate `wizard-bypass-admin`
  # whose email/login do NOT overlap with any Keycloak user, so OIDC's
  # find-or-create lands on a fresh record on first sign-in.
  "uid_field"                    => "preferred_username",
  "send_scope_to_token_endpoint" => true,
})
