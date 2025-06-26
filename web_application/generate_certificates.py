"""
Smart Plant Monitor - SSL Certificate Generation
Generates self-signed SSL certificates for HTTPS communication between NodeMCU ESP8266 and FastAPI backend server.
"""

import os
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime


def generate_ssl_certificates():
    """
    Generate self-signed SSL certificate for HTTPS server

    Creates certificate and private key files required for secure
    communication between NodeMCU sensors and FastAPI backend.

    Certificate with:
    - RSA 2048-bit encryption
    - 1-year validity period
    - SHA-256 signature algorithm

    Files Created:
    - certs/cert.pem: SSL certificate
    - certs/key.pem: Private key
    """
    print("Generating SSL certificates for Smart Plant Monitor...")

    # Create certificates directory
    os.makedirs("certs", exist_ok=True)

    # Generate RSA private key (2048-bit for security)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # Certificate subject and issuer information (self-signed)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IT"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Smart Plant Monitor"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    # Create certificate valid for 1 year
    cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now())
            .not_valid_after(datetime.datetime.now() + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.DNSName("127.0.0.1"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]), critical=False)
            .sign(private_key, hashes.SHA256())
            )

    # Save private key file
    with open("certs/key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Save certificate file
    with open("certs/cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print("SSL certificates generated successfully")
    print("Certificate: certs/cert.pem")
    print("Private key: certs/key.pem")
    print("Valid for: 365 days")


if __name__ == "__main__":
    print("Smart Plant Monitor - Self-signed SSL Certificate Generator")
    generate_ssl_certificates()