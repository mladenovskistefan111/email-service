# Known limitations

- Does not send email.
- `SIGTERM` is ignored when running as PID 1 (see Graceful shutdown).
- Image build uses the un-pinned `requirements.in`.
- Template placeholders `street_address_1/2` don't exist in the proto.
- Recipient addresses are logged.
