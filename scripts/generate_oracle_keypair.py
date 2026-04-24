"""Generate oracle keypair for Solana."""

import base58
from solders.keypair import Keypair as SoldersKeypair

from pathlib import Path
import inquirer


def generate_keypair() -> dict:
    """Generate a new oracle keypair."""
    keypair = SoldersKeypair()
    return {
        "public_key": str(keypair.pubkey()),
        "private_key": base58.b58encode(bytes(keypair)).decode(),
    }


def save_to_file(keypair: dict, path: str):
    """Save keypair to JSON file."""
    import json

    keypath = Path(path)
    keypath.parent.mkdir(parents=True, exist_ok=True)

    with open(keypath, "w") as f:
        json.dump({
            "public_key": keypair["public_key"],
            "private_key": keypair["private_key"],
        }, f, indent=2)

    print(f"Keypair saved to {path}")
    print(f"Public key: {keypair['public_key']}")


def main():
    """Main entry point."""
    print("Oracle Keypair Generator")
    print("=" * 40)

    questions = [
        inquirer.Path("path", message="Save path", path_type="file", default="./keys/oracle.json"),
    ]

    answers = inquirer.prompt(questions)

    keypair = generate_keypair()
    save_to_file(keypair, answers["path"])

    print("\nIMPORTANT: Add this public key to GlobalConfig.oracle in the Solana program!")
    print(f"Public key: {keypair['public_key']}")


if __name__ == "__main__":
    main()