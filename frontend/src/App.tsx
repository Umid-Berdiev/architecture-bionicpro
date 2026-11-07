import React from 'react';
import { ReactKeycloakProvider } from '@react-keycloak/web';
import Keycloak, { KeycloakConfig, KeycloakInitOptions } from 'keycloak-js';
import ReportPage from './components/ReportPage';

const keycloakConfig: KeycloakConfig = {
  url: process.env.REACT_APP_KEYCLOAK_URL,
  realm: process.env.REACT_APP_KEYCLOAK_REALM||"",
  clientId: process.env.REACT_APP_KEYCLOAK_CLIENT_ID||""
};

const keycloak = new Keycloak(keycloakConfig);

// Authorization Code flow with PKCE (RFC 7636): keycloak-js generates a code_verifier,
// sends its S256 code_challenge in the authorization request and proves possession of the
// verifier at the token endpoint, so an intercepted authorization code cannot be exchanged.
const keycloakInitOptions: KeycloakInitOptions = {
  pkceMethod: 'S256',
  onLoad: 'check-sso',
};

const App: React.FC = () => {
  return (
    <ReactKeycloakProvider authClient={keycloak} initOptions={keycloakInitOptions}>
      <div className="App">
        <ReportPage />
      </div>
    </ReactKeycloakProvider>
  );
};

export default App;
