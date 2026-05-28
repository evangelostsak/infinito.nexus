# Idempotently ensure an API-only bot user exists with a LOCAL password +
# Admin role for Basic-auth REST-API regression tests. Kept separate from
# the OIDC-managed `administrator` user (different login + email) so OIDC's
# first-sign-in user creation does not clash with this pre-seeded user's
# email (`Validation failed: Email address … is already used for another
# user.` — 422 from Zammad). Runs in every variant, including no-auth ones
# where Basic auth is the ONLY way the Playwright suite reaches the API.
#
# Expects the following ENV vars (set by the calling shell):
#
#   API_BOT_LOGIN     - login for the API-only bot user
#   API_BOT_EMAIL     - bot email (must NOT match the OIDC admin's email)
#   API_BOT_PASSWORD  - bot local password (Basic-auth secret)

UserInfo.current_user_id = 1

api_bot = User.find_or_initialize_by(login: ENV.fetch("API_BOT_LOGIN"))
api_bot.email     = ENV.fetch("API_BOT_EMAIL")
api_bot.firstname = ENV.fetch("API_BOT_FIRSTNAME")
api_bot.lastname  = ENV.fetch("API_BOT_LASTNAME")
api_bot.password  = ENV.fetch("API_BOT_PASSWORD")
api_bot.active    = true
api_bot.roles     = Role.where(name: %w[Admin Agent])
api_bot.save!

# Grant the api bot full access to the default `Users` group so it can
# create / read / change tickets via the REST API. Without an explicit group
# membership, `ticket.agent` permission alone yields 403 on POST /tickets.
users_group = Group.find_or_create_by!(name: "Users") { |g| g.active = true }
api_bot.group_names_access_map = { users_group.name => "full" }
api_bot.save!
