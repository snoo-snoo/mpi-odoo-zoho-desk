# Echo suppression is origin stamp plus unchanged hash

A write the connector just made must not be applied again (origin stamp). A payload that matches what we already have is skipped (external id + hash). Stamp-only still flickers Ticket fields; hash-only still ping-pongs Comments.
