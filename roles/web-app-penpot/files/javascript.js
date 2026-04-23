(function () {
  const authButtonLabels = [
    {
      selector: "a[href*='login-with-oidc'], button[formaction*='login-with-oidc']",
      label: 'Login with SSO'
    },
    {
      selector: '.main_ui_auth_login__login-ldap-button, .main_ui_auth_common__login-ldap-button',
      label: 'Login with LDAP'
    }
  ];

  function setButtonLabel(button, label) {
    const currentText = (button.textContent || '').replace(/\s+/g, ' ').trim();

    if (currentText === label && button.getAttribute('aria-label') === label) {
      return;
    }

    const textNodes = Array.from(button.childNodes).filter(function (node) {
      return node.nodeType === Node.TEXT_NODE;
    });

    textNodes.forEach(function (node) {
      button.removeChild(node);
    });

    button.appendChild(document.createTextNode(label));
    button.setAttribute('aria-label', label);
  }

  function syncAuthButtons() {
    authButtonLabels.forEach(function (entry) {
      const button = document.querySelector(entry.selector);

      if (button) {
        setButtonLabel(button, entry.label);
      }
    });
  }

  function init() {
    syncAuthButtons();

    if (!document.body) {
      return;
    }

    const observer = new MutationObserver(function () {
      syncAuthButtons();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
