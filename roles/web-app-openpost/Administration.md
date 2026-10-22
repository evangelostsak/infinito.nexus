# Administration

## Accounts and workspaces

OpenPost separates people (accounts) from the places they publish from (workspaces).
Connected social accounts, drafts, schedules and media belong to a workspace, and only its members see them.
Every member holds a workspace role, and only roles with publishing rights may publish or schedule.

The first account of a fresh instance becomes the instance admin.
The deploy registers the break-glass account first for that reason (see [Break-glass instance admin](#break-glass-instance-admin)).
Instance admins manage users, provider apps and instance settings under **Settings → Instance**; workspace owners invite members and assign their roles under **Settings → Workspace → Team**.

## Single sign-on

The role configures OpenPost's instance-wide OIDC provider against the shared Keycloak client (`OIDC.CLIENT.*`) whenever `web-app-keycloak` is deployed.

- Users sign in with the Keycloak button on the login page.
  OpenPost provisions them just in time on their first verified login (`OPENPOST_OIDC_JIT_ENABLED=true`) and matches later logins by issuer and subject.
- The platform `administrator` is listed in `OPENPOST_OIDC_BOOTSTRAP_ALLOWLIST` and becomes instance admin on its first SSO login.
- A just-in-time user starts without access to existing workspaces.
  Grant access by inviting the user from the workspace's team settings; OpenPost does not consume Keycloak groups.
- Password self-registration is closed.
  OpenPost gates password sign-up and just-in-time provisioning with the same switch, so with Keycloak deployed the role keeps `OPENPOST_DISABLE_REGISTRATIONS=false` and the shared proxy answers `POST /api/v1/auth/register` with HTTP 403; without Keycloak the switch itself is set.
- OpenPost ships no LDAP adapter, so the role declares no `ldap` service.
  Directory accounts sign in through Keycloak, which federates OpenLDAP, over OIDC.
- OpenPost never links an SSO identity to an existing account with the same e-mail address automatically.
  The break-glass account therefore uses its own address, and a person who already holds a local account keeps signing in with its password until an instance admin removes the local account and the person signs in through Keycloak again.
- For workspaces that require SSO, `OPENPOST_SSO_BREAK_GLASS_EMAILS` names instance admins that may still enter with their password plus TOTP or a passkey during an identity-provider outage.
  Add the break-glass address to that list through the inventory once the account has a second factor.
- OpenPost also offers a trusted-proxy sign-in (`OPENPOST_PROXY_AUTH_SECRET`, header `X-OpenPost-Proxy-User`).
  The role does not enable it; it is the fallback for a deployment that has to front OpenPost with `oauth2-proxy` instead of native OIDC, and it then requires the proxy to strip client-supplied `X-OpenPost-Proxy-*` headers.

## Break-glass instance admin

The deploy bootstraps the local account `web-app-openpost-breakglass` (username `openpost-breakglass`, password generated into the inventory) as the first OpenPost account, which makes it the instance admin.
Use it when Keycloak is unavailable: open `https://publish.<DOMAIN_PRIMARY>/` and sign in with the e-mail address and password from the inventory.
If the deploy reports that the break-glass account can neither sign in nor be registered, another account became the first instance admin or the password was changed in the UI; sign in with that account and reset the break-glass password, or restore the database from backup.

## Egress guard and relay

OpenPost protects itself against server-side request forgery with its `netguard` package.
Before it connects to a provider URL that a user entered, such as a Mastodon instance, it resolves the name and refuses the connection when any address lies in a private, loopback, CGNAT, link-local, documentation, benchmarking, multicast or reserved range.
It repeats the check when it dials and on every redirect, ignores proxy variables and offers no switch for built-in providers.

Inside an Infinito.Nexus deployment the sibling vhosts usually resolve to private addresses: the development stack, split-horizon DNS and WireGuard meshes all answer with RFC 1918 or mesh addresses.
The role therefore runs an `nginx` stream relay next to OpenPost:

- The role network uses `192.88.99.0/24`, the deprecated 6to4 relay anycast block (RFC 7526), which `netguard` accepts as a global unicast range and which never leaves the Docker host.
  `group_vars/all/08_networks.yml` lists the role in `NETWORK_ROLE_SUBNET_EXCEPTION_ROLES` for that reason.
- The relay carries the canonical domains of the deployed Mastodon, Pixelfed and PeerTube roles as network aliases, so OpenPost resolves those names to the relay.
- The relay reads the SNI of each TLS connection, forwards a mapped name unchanged to the shared OpenResty proxy and closes every other connection.
  It forwards to `host.docker.internal`, which points at the Docker host in compose and at the stack host in swarm.
- TLS stays end to end between OpenPost and OpenResty; in self-signed mode OpenPost trusts the platform CA through the compose CA injection.

Every destination that is not one of these aliases still passes through the guard unchanged.
A sibling instance that runs on another host is covered as long as the shared proxy of this host serves its vhost; a Fediverse instance outside the deployment needs no relay because it resolves to public addresses.
OpenPost's Mastodon registration accepts `https` on port 443 only, so the relay requires TLS on the sibling vhosts.

## Provider credentials

Developer app credentials live in the central `API` mapping of `group_vars/all/18_api.yml` and are overridden in the vault-encrypted inventory.
A network whose entry is incomplete (`lookup('api_enabled', '<provider>')` is false) is not configured in OpenPost and cannot be connected.

| `API` entry | OpenPost setting | Networks |
|---|---|---|
| `x` | `X_CLIENT_ID`, `X_CLIENT_SECRET` | X |
| `meta` | `OPENPOST_PROVIDER_APPS` entries `facebook` and `instagram` | Facebook Pages, Instagram |
| `threads` | `THREADS_CLIENT_ID`, `THREADS_CLIENT_SECRET` | Threads |
| `linkedin` | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | LinkedIn |
| `youtube` | `OPENPOST_PROVIDER_APPS` entry `youtube` | YouTube |
| `tiktok` | `OPENPOST_PROVIDER_APPS` entry `tiktok` | TikTok |

Mastodon, Pixelfed, PeerTube and Bluesky need no operator credentials: PeerTube exchanges the user's password once for tokens, and Bluesky uses an app password.
For Mastodon and Pixelfed the deploy registers an `OpenPost` app on every deployed sibling instance once, stores its credentials in `fediverse-apps.json` in the role's config directory and renders them into `MASTODON_SERVERS` and `PIXELFED_SERVERS`, named by the instance's canonical URL.
OpenPost v7.22.9 can register apps on any other instance by itself, but its code exchange then checks provider readiness against the bare host name the dialog sends and refuses with `provider operation is not ready: needs_configuration`; an external instance therefore needs the same pinning through those two variables.
Every callback URL has the form `https://publish.<DOMAIN_PRIMARY>/api/v1/accounts/<provider>/callback`.

## Networks

| Network | Post types | Developer app and account | Scopes | Review or verification | Quota | Cost (October 2026) | Token upkeep |
|---|---|---|---|---|---|---|---|
| Mastodon | Text, up to 4 images or one video, threads, scheduling | None; any instance, account of the user | `read write` | None | Set by the instance | None | Tokens do not expire |
| Pixelfed | Up to 4 photos, albums | None; any instance | `read write` | None | Set by the instance | None | Tokens do not expire |
| PeerTube | One video per post to one channel | None; instance username and password | Password exchanged once | None | Instance upload quota | None | OAuth tokens stored encrypted; the password is never stored |
| Bluesky | Text, up to 4 images or one MP4, threads | None; app password | App password | None | About 1,666 creates per hour | None | Sessions last up to 180 days and renew from the app password |
| Facebook Pages | Text, 1–10 images, public video URL, Stories, Reels | Meta Business app; Facebook Page | `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `business_management` and the further scopes in the upstream `.env.example` | Standard Access for app-role users without App Review; App Review for everyone else | Reels: 30 per Page per 24 h | No fee found | Long-lived Page tokens do not expire |
| Instagram | Images, carousels, Reels, Stories; no text-only posts | Meta app; Business or Creator account | `instagram_basic`, `instagram_content_publish`, `pages_show_list` and further scopes | App Review for non-role users | 100 per 24 h | No fee found | Instagram Login tokens last 60 days and refresh |
| X | Text (280 weighted characters), up to 4 images or one video, threads | X developer app with prepaid credits | `tweet.read`, `tweet.write`, `users.read`, `offline.access` | None beyond the developer agreement | 100 per 15 min per user | $0.015 per post, $0.20 per post with a URL | Access tokens refresh via `offline.access` |
| YouTube | One video or Short per post, no text or image posts | Google OAuth client; YouTube channel | `youtube.upload`, `youtube.readonly`, `userinfo.profile`, `userinfo.email` | Production status and Google verification for sensitive scopes | 100 `videos.insert` calls per day | No fee found | Testing-status refresh tokens expire after 7 days |
| LinkedIn | Text, images, documents, one MP4 | LinkedIn app; member or Organization Page | `openid`, `profile`, `w_member_social`; organization scopes need approval | Community Management API vetting of the legal entity | Development tier: 500 calls per app per day | No fee found | 60-day tokens without refresh |
| Threads | Text (500 characters), image or carousel, video | Meta app with the Threads product | `threads_basic`, `threads_content_publish` | App Review for non-role users | 250 per 24 h | No fee found | 60 days, refreshable |
| TikTok | One video or 1–35 photos; no text-only posts | TikTok developer app | `user.info.basic`, `video.publish`, `video.upload` | Content Posting API audit | About 15 per creator per day | No fee found | Not researched |

Sources: the [OpenPost provider reference](https://github.com/getopenpost/openpost/blob/0deadaf7bbf3b3be045e783c3eeef323c9e3c440/docs/reference/providers/index.md), its [environment variables](https://github.com/getopenpost/openpost/blob/0deadaf7bbf3b3be045e783c3eeef323c9e3c440/docs/reference/configuration/environment-variables.md) and the platform sources listed in the role's requirement.

## Unsupported features and workarounds

| Limitation | Workaround |
|---|---|
| TikTok's content sharing guidelines reject in-house upload tools as a use case for the Content Posting API. | Publish to TikTok manually, or apply with a use case TikTok accepts; keep TikTok credentials empty until then. |
| X charges $0.20 instead of $0.015 for a post that contains a URL. | Write the X rendition without links, or accept the surcharge per post. |
| X forbids identical content across accounts of the same owner. | Give each X account its own rendition. |
| OpenPost's X budget guardrail (`OPENPOST_X_MONTHLY_BUDGET_MICROUSD`) applies only in its cloud edition. | Cap X spending through the prepaid credits of the X developer account. |
| Instagram accepts JPEG only and fetches media from a public URL. | Deploy `web-app-seaweedfs` so media gets public HTTPS URLs; convert other image formats before upload. |
| Facebook, Instagram, Threads and TikTok fetch media from public HTTPS URLs. | Same as above; without `web-app-seaweedfs` media is served under `/media/` of the public OpenPost domain, which also works when that domain is reachable from the internet. |
| LinkedIn requires vetting of the legal entity and re-authorisation every 60 days. | Plan the vetting before launch and schedule a re-authorisation reminder. |
| YouTube projects in testing status lose refresh tokens after 7 days. | Move the Google OAuth client to production status and complete verification. |
| Bluesky is also reachable without OpenPost through `web-app-bridgy-fed`. | Use the bridge for automatic federation and OpenPost for deliberate Bluesky-native posts. |
| Sibling Fediverse instances are reachable only over TLS on port 443. | Keep TLS enabled for `web-app-mastodon`, `web-app-pixelfed` and `web-app-peertube`. |

## Data processing and dependencies

- Every network receives exactly what a user publishes to it: the rendition text, attached media, alt text and post settings, plus the OAuth tokens of the connected account.
- Facebook, Instagram, Threads and TikTok additionally download the attached media from its public URL.
- Provider tokens and provider-app secrets are stored in Postgres encrypted with AES-256-GCM under `OPENPOST_ENCRYPTION_KEY`; the key lives in the inventory and is needed to restore a backup.
- Diagnostics, the update check, PostHog telemetry, the feedback form, public profiles, stock media search and workflow AI are disabled, so the instance sends nothing to OpenPost's maintainers or to AI providers.
- Third-party dependencies at runtime are the APIs of the connected networks only.
- OpenPost is licensed AGPL-3.0-only.
  The role deploys the unmodified upstream image and links its source, which satisfies the AGPL's source-offer obligation for network users; the role's own files remain under the Infinito.Nexus Community License.

## Backup, restore and upgrades

- With `web-app-seaweedfs` deployed, browsers upload media directly to its public S3 vhost through presigned URLs, which is why `OPENPOST_S3_ENDPOINT` is the public endpoint and the CSP allows it in `connect-src`; OpenPost deduplicates identical files by content hash.
- The platform backup covers the OpenPost database in the shared Postgres and the `openpost_media` volume; media in `web-app-seaweedfs` is covered by that role's backup.
- A restore needs the database, the media and the inventory secrets, especially `encryption_key`; without it the stored provider tokens cannot be decrypted and every network has to be reconnected.
- Changing the pinned version in `meta/services.yml` and redeploying runs OpenPost's own migrations, which take a Postgres advisory lock.
  Only the latest upstream release receives security fixes, so follow new release tags promptly.

## Staging checklist

Run these checks against real platforms after onboarding a network and after every OpenPost upgrade:

1. Connect the account in a staging workspace and confirm OpenPost shows it as connected.
2. Publish a text post (where supported), an image post and a video post immediately.
3. Schedule a post five minutes ahead and confirm it appears on time.
4. Open each published post through the link in OpenPost.
5. Disconnect the account and reconnect it to confirm token renewal.
6. Record the result in the matrix below.

## Verified combinations

| Network | Content type | OpenPost version | Date | Result |
|---|---|---|---|---|
| Mastodon (local instance) | Text | v7.22.9 | pending | CI end-to-end test |
| Pixelfed (local instance) | Image | v7.22.9 | pending | CI end-to-end test |
| PeerTube (local instance) | Video | v7.22.9 | pending | CI end-to-end test |
| Facebook Pages | Text, image | v7.22.9 | not yet verified | Manual staging check |
| Instagram | Image | v7.22.9 | not yet verified | Manual staging check |
| X | Text | v7.22.9 | not yet verified | Manual staging check |
| YouTube | Video | v7.22.9 | not yet verified | Manual staging check |
