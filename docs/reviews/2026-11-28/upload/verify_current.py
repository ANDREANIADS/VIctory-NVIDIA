"""Run the unchanged packaged PR 60 verifier on the rebased commits after verifying the known blob IDs."""
import sys
sys.dont_write_bytecode = True
import verify

parent = "ef87380ac02b2ecfce6673782be5a37e3dd7d9f3"
head = "cf9a417b170941a0102b000413c09cce4ea2a969"
verify.BLOBS[parent] = verify.BLOBS[verify.OLD]
verify.BLOBS[head] = verify.BLOBS[verify.FIX]
verify.OLD, verify.FIX = parent, head
verify.main()
