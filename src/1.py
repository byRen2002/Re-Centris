from Crypto.PublicKey import RSA
from Crypto.Cipher import AES
from pkcs1 import encode, decode
import os
import hashlib
import signal


FLAG = os.getenv("FLAG", "wdflag{******************************}")

class RSA_OT:
    
    def __init__(self, key: RSA):
        self.key = key
        self.n = key.n
        self.e = key.e
        self.d = key.d
        self.nbyte = key.size_in_bytes()
        
    @staticmethod
    def new(nbits: int) -> "RSA_OT":
        key = RSA.generate(nbits)
        return RSA_OT(key)
        
    def encrypt(self, message: bytes) -> bytes:
        padded = encode(message, self.nbyte)
        ct = self.key._encrypt(padded)
        return int(ct).to_bytes(self.nbyte, "big")
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        padded = self.key._decrypt(int.from_bytes(ciphertext, "big"))
        return decode(padded)
    
    def show_public_key(self):
        print("[+] n =", self.n)
        print("[+] e =", self.e)
        
    def run(self, m0, m1):
        print("[+] OT Protocol Starts")
        m0 = int.from_bytes(encode(m0, self.nbyte), "big")
        m1 = int.from_bytes(encode(m1, self.nbyte), "big")
        x0 = int.from_bytes(os.urandom(self.nbyte), "big") % self.n
        x1 = int.from_bytes(os.urandom(self.nbyte), "big") % self.n
        print(f"[+] x0 = {x0}")
        print(f"[+] x1 = {x1}")
        v = int(input("[+] v = "))
        M0 = (m0 + pow(v - x0, self.d, self.n)) % self.n
        M1 = (m1 + pow(v - x1, self.d, self.n)) % self.n
        print(f"[+] M0 = {M0}")
        print(f"[+] M1 = {M1}")
        print("[+] OT Protocol Ends")
        
def xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))
        
def challenge(rounds = 70):
    aes_key = os.urandom(32)
    xor_key = os.urandom(32)
    aes = AES.new(aes_key, AES.MODE_ECB)
    rsa_ot = RSA_OT.new(1024)
    secrets = [os.urandom(32) for i in range(rounds)]
    message_pairs = [(aes_key, xor_key)]
    message_pairs += [(aes.encrypt(secret), xor(xor_key, secret)) for secret in sec