const { test, expect } = require("@playwright/test");
const { normalizeBaseUrl, decodeDotenvQuotedValue } = require("./personas");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { resolveTimeout } = require("./timeouts");

const baseUrl = normalizeBaseUrl(process.env.OPENBAO_BASE_URL || "");
const kvMount = decodeDotenvQuotedValue(process.env.OPENBAO_KV_MOUNT || "infinito");

const ACCOUNTS = {
  administrator: {
    username: decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || ""),
    password: decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || ""),
  },
  operator: {
    username: decodeDotenvQuotedValue(process.env.BAO_OPERATOR_USERNAME || ""),
    password: decodeDotenvQuotedValue(process.env.BAO_OPERATOR_PASSWORD || ""),
  },
  reader: {
    username: decodeDotenvQuotedValue(process.env.BAO_READER_USERNAME || ""),
    password: decodeDotenvQuotedValue(process.env.BAO_READER_PASSWORD || ""),
  },
};

const RBAC_ROLES = Object.keys(ACCOUNTS);

test.use({ ignoreHTTPSErrors: true });

async function login(request, role) {
  const { username, password } = ACCOUNTS[role];
  const response = await request.post(
    `${baseUrl}/v1/auth/ldap/login/${encodeURIComponent(username)}`,
    { data: { password }, failOnStatusCode: false, timeout: resolveTimeout(30_000) },
  );
  expect(
    response.status(),
    `expected the LDAP auth method to accept '${username}' (${role}), got ${response.status()}`,
  ).toBe(200);

  const body = await response.json();
  return { policies: body.auth.policies || [], token: body.auth.client_token };
}

test("rbac: each role group maps its member to exactly its own policy", async ({ request }) => {
  skipUnlessServiceEnabled("ldap");

  for (const role of RBAC_ROLES) {
    const { policies } = await login(request, role);
    expect(policies, `'${role}' must receive the '${role}' policy`).toContain(role);

    for (const other of RBAC_ROLES.filter((candidate) => candidate !== role)) {
      expect(
        policies,
        `'${role}' must not receive the '${other}' policy, got ${policies.join(", ")}`,
      ).not.toContain(other);
    }
  }
});

test("rbac: the operator may write an application secret and the reader may not", async ({ request }) => {
  skipUnlessServiceEnabled("ldap");

  const secretPath = `${baseUrl}/v1/${kvMount}/data/playwright/rbac-probe`;
  const payload = { data: { data: { probe: "operator-write" } } };

  const operator = await login(request, "operator");
  const operatorWrite = await request.post(secretPath, {
    headers: { "X-Vault-Token": operator.token },
    data: payload,
    failOnStatusCode: false,
    timeout: resolveTimeout(30_000),
  });
  expect(
    [200, 204],
    `the operator must be able to write an application secret, got ${operatorWrite.status()}`,
  ).toContain(operatorWrite.status());

  const reader = await login(request, "reader");
  const readerWrite = await request.post(secretPath, {
    headers: { "X-Vault-Token": reader.token },
    data: payload,
    failOnStatusCode: false,
    timeout: resolveTimeout(30_000),
  });
  expect(
    readerWrite.status(),
    `the reader must be refused write access, got ${readerWrite.status()}`,
  ).toBe(403);

  const readerRead = await request.get(secretPath, {
    headers: { "X-Vault-Token": reader.token },
    failOnStatusCode: false,
    timeout: resolveTimeout(30_000),
  });
  expect(
    readerRead.status(),
    `the reader must be able to read the secret the operator wrote, got ${readerRead.status()}`,
  ).toBe(200);
});

test("rbac: only the administrator may read the ACL policy definitions", async ({ request }) => {
  skipUnlessServiceEnabled("ldap");

  const policyPath = `${baseUrl}/v1/sys/policies/acl/operator`;

  const administrator = await login(request, "administrator");
  const adminRead = await request.get(policyPath, {
    headers: { "X-Vault-Token": administrator.token },
    failOnStatusCode: false,
    timeout: resolveTimeout(30_000),
  });
  expect(
    adminRead.status(),
    `the administrator must be able to read a policy definition, got ${adminRead.status()}`,
  ).toBe(200);

  for (const role of ["operator", "reader"]) {
    const { token } = await login(request, role);
    const response = await request.get(policyPath, {
      headers: { "X-Vault-Token": token },
      failOnStatusCode: false,
      timeout: resolveTimeout(30_000),
    });
    expect(
      response.status(),
      `'${role}' must be refused the policy definitions, got ${response.status()}`,
    ).toBe(403);
  }
});
