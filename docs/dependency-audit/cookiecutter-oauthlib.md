# cookiecutter + oauthlib — dependency audit (DDGS)

Versions observed: `cookiecutter 2.7.1`, `oauthlib 3.3.1`.
Provenance: neither is a DDGS runtime dependency. `cookiecutter` is pulled by
`flet-cli` (`flet create` / `flet build` template rendering); `oauthlib` is
pulled by `flet` and used only inside `flet.auth.authorization_service`.
`src/` contains **zero** imports of either package (verified by grep).
App policy (README): **"No account, ever. No sign-up, no login."**

## 1. API inventory

### 1a. cookiecutter — project templating API

Entry point — `main.cookiecutter(template, checkout, no_input,
extra_context, replay, overwrite_if_exists, output_dir, config_file,
default_config, password, directory, skip_if_file_exists, accept_hooks,
keep_project_on_failure) -> str` (returns generated project dir).

| Module | Key API |
|---|---|
| `generate` | `generate_context()` (cookiecutter.json + default/extra overrides, choice/multichoice/dict/bool handling); `generate_files()` / `generate_file()` (Jinja render, binary passthrough via binaryornot, `_copy_without_render`, `_new_lines`); `render_and_create_dir()`; `apply_overwrites_to_context()` |
| `prompt` | `prompt_for_config()` (two-pass: scalars/choices then dicts, `__prompts__` labels, `no_input` passthrough); `read_user_variable/yes_no/choice/dict`, `choose_nested_template()`, `prompt_and_delete()`, `render_variable()`; `YesNoPrompt`, `JsonPrompt` (rich-based) |
| `repository` | `determine_repo_dir()` (local dir → zip → git/hg clone); `expand_abbreviations()` (`gh:`/`gl:`/`bb:`); `is_repo_url()`, `is_zip_file()`, `repository_has_cookiecutter_json()` |
| `config` | `get_user_config()` / `get_config()` (`~/.cookiecutterrc`, `COOKIECUTTER_CONFIG` env); `merge_configs()`; `DEFAULT_CONFIG` (`~/.cookiecutters/`, `~/.cookiecutter_replay/`) |
| `replay` | `dump()` / `load()` — replay prior answers from JSON, mutually exclusive with `no_input`/`extra_context` |
| `hooks` | `run_hook_from_repo_dir()` (`pre_gen_project` / `post_gen_project`, Jinja-rendered then executed); `run_pre_prompt_hook()` (copies repo to tmp dir first); `find_hook()`, `run_script()` |
| `environment` | `StrictEnvironment` (StrictUndefined — undefined vars raise); auto-loads `Jsonify/RandomString/Slugify/UUID/Time` Jinja extensions + template `_extensions` |
| `find` | `find_template()` — child dir containing `{{ cookiecutter… }}` |
| `utils` | `work_in()`, `rmtree()`, `make_sure_path_exists()`, `create_env_with_context()`, `create_tmp_repo_dir()` |
| `vcs` | `clone()` (git/hg subprocess, `checkout` branch/tag), `identify_repo()`, `is_vcs_installed()` |
| `zipfile` | `unzip()` — `requests.get(stream, timeout=100)` download + extractall to temp dir, password retry loop |
| `exceptions` | 16 typed errors (`RepositoryNotFound/CloneFailed`, `FailedHookException`, `UndefinedVariableInTemplate`, `OutputDirExistsException`, …) |
| `cli` / `log` | click CLI (`main`, `validate_extra_context`, `list_installed_templates`); `configure_logger()` |

flet-cli call sites: `flet_cli/commands/create.py` (`flet create … no_input=True,
overwrite_if_exists=True, extra_context=template_data`) and
`commands/build_base.py` (Pyodide build template render).

### 1b. oauthlib — OAuth 1 / OAuth 2 / OIDC capability map

PKCE: **yes** — `WebApplicationClient.prepare_request_uri(code_challenge,
code_challenge_method)` + `prepare_request_body(code_verifier)`,
`Client.create_code_verifier/create_code_challenge`, server-side
`AuthorizationCodeGrant.validate_code_challenge` (`S256` + `plain`).
JWT: **yes, server-issuance only** — `openid JWTToken` (delegates to
validator `get_jwt_bearer_token`), `common.generate_signed_token /
verify_signed_token`, `ServiceApplicationClient` (JWT-bearer grant),
RSA helpers in oauth1 `signature.py` (PyJWT-backed). No general JOSE
validation toolkit.

Grant types (client + server halves both present):

| Grant | Client | Server grant | Notes |
|---|---|---|---|
| Authorization code | `WebApplicationClient` (+PKCE) | `AuthorizationCodeGrant` | Full flow incl. `state` enforcement (`MismatchingStateError`) |
| Implicit | `MobileApplicationClient` | `ImplicitGrant` | Legacy; token-in-fragment, no refresh — avoid |
| Client credentials | `BackendApplicationClient` | `ClientCredentialsGrant` | Machine-to-machine |
| Resource-owner password | `LegacyApplicationClient` | `ResourceOwnerPasswordCredentialsGrant` | Direct password handling — never in client apps |
| Refresh token | `Client.prepare_refresh_body` | `RefreshTokenGrant` | Rotation supported (`rotate_refresh_token`) |
| Device code (RFC 8628) | `DeviceClient` | `DeviceCodeGrant` + `DeviceAuthorizationEndpoint` | Polling; `AuthorizationPending/SlowDown/ExpiredToken` errors |
| JWT bearer | `ServiceApplicationClient` | via validator hooks | No user-approval step |
| OIDC (code/hybrid/implicit) | — (server lib) | `openid…AuthorizationCodeGrant/HybridGrant/ImplicitGrant` + dispatchers | `JWTToken`, `UserInfoEndpoint`, OIDC exceptions |

Token handling: `BearerToken` / `OAuth2Token` (scope tracking),
`prepare_bearer_headers` (recommended) vs `prepare_bearer_uri`
(discouraged), experimental MAC (`prepare_mac_header`, hmac-sha-1/256).
Server endpoints: `AuthorizationEndpoint`, `TokenEndpoint`,
`ResourceEndpoint.verify_request`, `RevocationEndpoint`,
`IntrospectEndpoint`, `MetadataEndpoint`, pre-configured `Server /
WebApplicationServer / …`. `RequestValidator` (~30 overridable methods:
redirect-uri, scopes, PKCE, token save/validate, introspection).
`parameters.py`: `prepare_grant_uri / prepare_token_request /
parse_authorization_code_response / parse_implicit_response /
parse_token_response`. `common.py`: `Request`, `generate_nonce /
generate_timestamp / generate_token / generate_client_id`,
`is_secure_transport` (HTTPS enforcement).

oauth1 / RFC 5849 (one line each): `Client` — full 1.0a client (temp-token,
authorize, sign); `signature.py` — HMAC-SHA1/256/512, RSA-SHA1/256/512,
PLAINTEXT sign/verify + base-string/normalization; `parameters.py` —
header/body/query param placement; `endpoints/{base,request_token,
authorization,access_token,resource,signature_only,pre_configured}` —
server-side three-legged flow incl. `WebApplicationServer`;
`request_validator.py` — ~25-method server contract (client/token secrets,
nonce/timestamp, realms, verifier); `errors.py` — 4 typed errors;
`utils.py` — header/list/escape parsers.

What flet actually uses (the only live consumer): `flet.auth` imports
`WebApplicationClient` in three spots of `authorization_service.py` —
`get_authorization_data` (URL + `secrets.token_urlsafe(16)` state, PKCE
passthrough from `OAuthProvider.code_challenge/_method/_verifier`),
`request_token` (code exchange), `__refresh_token` (expiry-gated refresh).
Bundled providers: Google, GitHub, Azure, Auth0. DDGS calls none of it
(no `Page.login` / `OAuthProvider` usage anywhere in `src/`).

## 2. Strategic verdict

**cookiecutter — BALLAST at runtime, keep as build tooling.**
It exists for `flet create` / `flet build`, never for the shipped app; it is
not in `[project].dependencies` and `src/` never imports it. Utilization 0%
by design, and that is correct. Niche optional upside only: deterministic
offline scaffolding of new screens/engines via a *local* template with
`no_input=True + extra_context` (replay files give reproducible runs) —
but that is a dev-script convenience, not a product capability. Do not
vendor it, do not add it to runtime deps, do not fetch remote templates in
any automation.

**oauthlib — BALLAST at runtime, untouchable transitive dep, 0% utilization
mandated by policy.** It rides under `flet.auth`; the app's "No account,
ever" policy rules out every user-facing flow it implements. Assessed
against the bypass scenarios, honestly: (a) premium-license OAuth — no
license server exists, rejected; (b) provider integrations for the AI
gateway — providers take user-pasted API keys, no OAuth involved,
rejected; (c) future optional sync via `Page.login` + Google/GitHub with
PKCE-S256 — technically the only real fit, but it contradicts current
policy and needs a policy reversal first, so parked, not planned. Cannot be
pruned (flet hard-depends on it). Verdict: leave it, use 0% of it.

## 3. Gotchas

cookiecutter: remote templates are arbitrary-code execution — `git clone`
of an unpinned URL (mutable branch/tag, `gh:` abbreviations hide the real
source) plus `pre/post_gen_project` hooks rendered with Jinja and run via
`subprocess.Popen` (`shell=True` on Windows); `pre_prompt` hooks run before
any prompt. Zip path downloads with `requests` and no hash pinning, then
`extractall` to a temp dir. `_patch_import_path_for_repo` appends the
template dir to `sys.path` (template code importable). `replay` and
`no_input`/`extra_context` are mutually exclusive (raises). Cached clones
in `~/.cookiecutters/` can go stale.
oauthlib: `redirect_uri` must be pre-registered and string-compared
(`MismatchingRedirectURIError`); always send and verify `state`
(CSRF — flet does this for you); enforce PKCE-`S256`, never `plain`, with a
high-entropy verifier; never use implicit or password grants in shipped
code; put bearer tokens in the `Authorization` header, never the URI;
`is_secure_transport` rejects non-HTTPS (except localhost); rotate refresh
tokens and handle expiry (`expires_at` may be absent → flet skips refresh);
device flow must honor polling intervals (`SlowDownError`); validate scopes
on every token response (`scope_changed` signal exists for this).

## 4. Coverage

- cookiecutter: **18/18 files** — 13 full reads (`main`, `generate`,
  `prompt`, `repository`, `replay`, `hooks`, `config`, `utils`, `vcs`,
  `exceptions`, `find`, `environment`, `zipfile`), 5 skimmed via
  targeted grep/cat (`cli`, `extensions`, `log`, `__init__`, `__main__`).
- oauthlib: **75/75 files** — 6 full reads (`common` core, `oauth2/__init__`,
  `clients/web_application`, `tokens` bearer/MAC, flet
  `authorization_service`, OIDC `tokens.JWTToken`), remainder covered by
  class/method enumeration of every grant, client, endpoint, validator,
  signature and error module.
- Consumer side: `src/` grep (zero hits), `uv.lock` provenance, `pyproject`
  deps, `flet_cli` call sites, `flet.auth` providers — all verified.
