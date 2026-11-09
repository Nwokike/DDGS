"""Which distribution channel this build is for.

Two values exist:

- ``"direct"`` - every build by default: the direct APKs from GitHub
  Releases, desktop, and web. Premium is sold through the Kiri License
  Worker (Flutterwave: card, bank transfer, USDC), and Google Play Billing
  rows appear if the store ever lists products for this package.
- ``"play"`` - the AAB uploaded to Google Play. Premium purchase UI does
  not exist on it. Google requires a Google Payments merchant profile to
  sell in-app digital goods, and no account available to us has one yet,
  so the Play build is free-only: 50 credits a day and ads, exactly as
  before Premium existed. Nothing is declared to Google, and no request
  ever reaches the licence Worker. The same channel also blocks YouTube
  downloads (Play Developer Policy): the video downloader shows the
  restriction dialog instead of resolving a stream. The Assistant's own
  downloader is NOT gated - it downloads what the user asked it to.

The workflow's AAB job rewrites this one line before building, so the
policy is baked into the artifact and nothing is decided at runtime.
There is no second branch carrying a copy of this policy: both Play
gates (premium and YouTube) live in main and switch on this one value.
"""

CHANNEL = "direct"

__all__ = ["CHANNEL"]
