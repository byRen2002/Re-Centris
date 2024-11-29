# SageMath version 10.0, Release Date: 2023-05-20

from sage.all import *
from Crypto.Util.number import *

from secret import flag
flag = flag.lstrip(b"wdflag{").rstrip(b"}")

class ShamirSS:
    def __init__(self, coefs, value):
        self.coefs = coefs
        self.value = value

class ShamirProtocol:
    def __init__(self, n_players, threshold, modulus):
        self.n_players = n_players
        self.threshold = threshold
        
        assert isPrime(modulus), "Modulus must be a prime number"
        self.modulus = modulus
        
        
    def input_share(self, values):
        coefs = [
            [getRandomRange(1, self.modulus) for _ in range(self.threshold)]
            for _ in range(self.n_players)
        ]

        randoms = values + [getRandomRange(1, self.modulus) for _ in range(self.threshold - len(values))]

        values = [
            sum([r * c for r, c in zip(randoms, coef)]) % self.modulus
            for coef in coefs
        ]

        shares = [ShamirSS(coef, value) for coef, value in zip(coefs, values)]
        return shares
    


protocol = ShamirProtocol(len(flag), len(flag) * 2, 257)
values = list(flag)

import os
os.mkdir("shares")

for i in range(10000):
    shares = protocol.input_share(values)
    save(shares, f"shares/share_{i}.sobj")