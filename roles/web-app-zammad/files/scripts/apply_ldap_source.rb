# Idempotently configure Zammad's LdapSource against the central
# svc-db-openldap server. With this in place Zammad accepts inetOrgPerson
# bind authentication against the regular sign-in form for users present
# in the directory; new logins are auto-provisioned as Customers (Admin
# role mapping is handled separately by the group-role mapper, not here).
#
# Expects the following ENV vars (set by the calling shell):
#
#   LDAP_NAME       - human-readable LdapSource record name
#   LDAP_HOST       - LDAP server hostname (docker DNS name within the openldap network)
#   LDAP_PORT       - LDAP server port (numeric, plain LDAP — STARTTLS off in-cluster)
#   LDAP_BASE_DN    - base DN under which user entries live (ou=users,dc=...)
#   LDAP_BIND_DN    - bind DN used by Zammad to read the directory
#   LDAP_BIND_PW    - bind DN password
#   LDAP_UID_ATTR   - attribute that carries the login (uid for inetOrgPerson)

UserInfo.current_user_id = 1

source = LdapSource.find_or_initialize_by(name: ENV.fetch("LDAP_NAME"))
source.preferences = {
  "host_url"          => "ldap://#{ENV.fetch('LDAP_HOST')}:#{ENV.fetch('LDAP_PORT')}",
  "ssl"               => "off",
  "ssl_verify"        => false,
  "bind_user"         => ENV.fetch("LDAP_BIND_DN"),
  "bind_pw"           => ENV.fetch("LDAP_BIND_PW"),
  "base_dn"           => ENV.fetch("LDAP_BASE_DN"),
  "user_filter"       => "(objectClass=inetOrgPerson)",
  "user_uid"          => ENV.fetch("LDAP_UID_ATTR"),
  "user_attributes"   => {
    ENV.fetch("LDAP_UID_ATTR") => "login",
    "givenName"                => "firstname",
    "sn"                       => "lastname",
    "mail"                     => "email",
  },
  "group_filter"      => "(objectClass=groupOfNames)",
  "group_uid"         => "dn",
  "group_role_map"    => {},
  "unassigned_users"  => "skip_sync",
}
source.active = true
source.save!
