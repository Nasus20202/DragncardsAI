import Config

# Use the local in-memory adapter in dev so email sending doesn't crash.
# Sent emails are stored in memory and visible at http://localhost:4000/dev/mailbox
config :dragncards, DragnCardsWeb.PowMailer,
  adapter: Swoosh.Adapters.Local
