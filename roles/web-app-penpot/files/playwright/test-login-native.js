// Native (local-DB) login: the administrator authenticates with the
// email/password form ("Login" button). The role bootstraps a local password
// for the administrator profile (tasks/main.yml) so this path works alongside
// OIDC/LDAP.
exports.register = (shared) => {
  const { test, expect, env, penpotNativeLogin } = shared;

  test("native: administrator local password login", async ({ page }) => {
    test.setTimeout(90_000);
    expect(env.adminEmail, "ADMIN_EMAIL must be set").toBeTruthy();
    expect(env.adminPassword, "ADMIN_PASSWORD must be set").toBeTruthy();
    await penpotNativeLogin(page, env.adminEmail, env.adminPassword);
  });
};
