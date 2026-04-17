from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]


def sign_and_send(w3, tx, private_key):
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt


def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
        #YOUR CODE HERE
    
    source_info = get_contract_info("source", contract_info)
    dest_info = get_contract_info("destination", contract_info)

    with open(contract_info, "r") as f:
        contracts = json.load(f)

    private_key = contracts.get("warden_private_key")
    if not private_key:
        raise ValueError("No warden private key found")

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    acct = Web3().eth.account.from_key(private_key)
    sender = acct.address

    source_info = contracts["source"]
    dest_info = contracts["destination"]

    source_w3 = connect_to("source")
    dest_w3 = connect_to("destination")

    source_contract = source_w3.eth.contract(
        address=Web3.to_checksum_address(source_info["address"]),
        abi=source_info["abi"]
    )
    dest_contract = dest_w3.eth.contract(
        address=Web3.to_checksum_address(dest_info["address"]),
        abi=dest_info["abi"]
    )

    if chain == "source":
        latest = source_w3.eth.block_number
        start_block = max(0, latest - 4)
        end_block = latest

        print(f"Scanning source blocks {start_block} to {end_block}")

        event_filter = source_contract.events.Deposit.create_filter(
            from_block=start_block,
            to_block=end_block
        )
        events = event_filter.get_all_entries()

        if len(events) == 0:
            print("No Deposit events found")
            return

        nonce = dest_w3.eth.get_transaction_count(sender)

        for evt in events:
            token = evt["args"]["token"]
            recipient = evt["args"]["recipient"]
            amount = evt["args"]["amount"]

            print(f"Deposit found: token={token}, recipient={recipient}, amount={amount}")

            tx = dest_contract.functions.wrap(
                Web3.to_checksum_address(token),
                Web3.to_checksum_address(recipient),
                int(amount)
            ).build_transaction({
                "from": sender,
                "nonce": nonce,
                "gas": 500000,
                "gasPrice": dest_w3.eth.gas_price,
                "chainId": 97
            })

            receipt = sign_and_send(dest_w3, tx, private_key)
            print(f"wrap() tx sent: {receipt.transactionHash.hex()}")
            nonce += 1

    elif chain == "destination":
        latest = dest_w3.eth.block_number
        start_block = max(0, latest - 4)
        end_block = latest

        print(f"Scanning destination blocks {start_block} to {end_block}")

        event_filter = dest_contract.events.Unwrap.create_filter(
            from_block=start_block,
            to_block=end_block
        )
        events = event_filter.get_all_entries()

        if len(events) == 0:
            print("No Unwrap events found")
            return

        nonce = source_w3.eth.get_transaction_count(sender)

        for evt in events:
            underlying_token = evt["args"]["underlying_token"]
            recipient = evt["args"]["to"]
            amount = evt["args"]["amount"]

            print(f"Unwrap found: underlying={underlying_token}, recipient={recipient}, amount={amount}")

            tx = source_contract.functions.withdraw(
                Web3.to_checksum_address(underlying_token),
                Web3.to_checksum_address(recipient),
                int(amount)
            ).build_transaction({
                "from": sender,
                "nonce": nonce,
                "gas": 500000,
                "gasPrice": source_w3.eth.gas_price,
                "chainId": 43113
            })

            receipt = sign_and_send(source_w3, tx, private_key)
            print(f"withdraw() tx sent: {receipt.transactionHash.hex()}")
            nonce += 1


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python bridge.py [source|destination] [contract_info.json]")
        sys.exit(1)

    chain = sys.argv[1]
    contract_info_file = "contract_info.json"
    if len(sys.argv) > 2:
        contract_info_file = sys.argv[2]

    scan_blocks(chain, contract_info_file)
