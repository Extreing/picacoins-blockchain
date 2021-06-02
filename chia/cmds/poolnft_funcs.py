import asyncio
import json
import time
from pprint import pprint

from chia.pools.pool_puzzles import launcher_id_to_p2_puzzle_hash
from chia.pools.pool_wallet_info import PoolWalletInfo, PoolSingletonState
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.util.bech32m import encode_puzzle_hash
from chia.util.byte_types import hexstr_to_bytes
from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.wallet.transaction_record import TransactionRecord
from chia.wallet.util.wallet_types import WalletType
import aiohttp


async def create(args: dict, wallet_client: WalletRpcClient, fingerprint: int) -> None:
    pool_url = args["pool_url"]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{pool_url}/pool_info") as response:
                if response.ok:
                    json_dict = json.loads(await response.text())
                else:
                    print(f"Response not OK: {response.status}")
                    return
    except Exception as e:
        print(f"Error connecting to pool {pool_url}: {e}")
        return

    if json_dict["relative_lock_height"] > 1000:
        print("Relative lock height too high for this pool, cannot join")
        return

    print(f"Will create a pool NFT and join pool: {pool_url}.")
    pprint(json_dict)
    user_input: str = input("Confirm [n]/y: ")
    if user_input.lower() == "y" or user_input.lower() == "yes":
        try:
            tx_record: TransactionRecord = await wallet_client.create_new_pool_wallet(
                hexstr_to_bytes(json_dict["target_puzzle_hash"]),
                pool_url,
                json_dict["relative_lock_height"],
                "localhost:5000",
            )
            start = time.time()
            while time.time() - start < 10:
                await asyncio.sleep(0.1)
                tx = await wallet_client.get_transaction(1, tx_record.name)
                if len(tx.sent_to) > 0:
                    print(f"Transaction submitted to nodes: {tx.sent_to}")
                    print(f"Do chia wallet get_transaction -f {fingerprint} -tx 0x{tx_record.name} to get status")
                    return None
        except Exception as e:
            print(f"Error creating pool NFT: {e}")
        return
    print("Aborting.")


def pprint_pool_wallet_state(pool_wallet_info: PoolWalletInfo, address_prefix: str):
    print(f"Current state: {PoolSingletonState(pool_wallet_info.current.state).name}")
    print(f"Target address: {encode_puzzle_hash(pool_wallet_info.current.target_puzzle_hash, address_prefix)}")
    print(f"Pool URL: {pool_wallet_info.current.pool_url}")
    print(f"Owner public key: {pool_wallet_info.current.owner_pubkey}")
    print(f"Relative lock height: {pool_wallet_info.current.relative_lock_height} blocks")
    print(f"Launcher ID: {pool_wallet_info.launcher_id}")
    print(
        f"P2 singleton address (pool contract address for plotting):"
        f" {encode_puzzle_hash(launcher_id_to_p2_puzzle_hash(pool_wallet_info.launcher_id), address_prefix)}"
    )
    if pool_wallet_info.target is not None:
        print(f"Target state: {PoolSingletonState(pool_wallet_info.target.state).name}")
        print(f"Pool URL: {pool_wallet_info.target.pool_url}")


async def show(args: dict, wallet_client: WalletRpcClient, fingerprint: int) -> None:
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    address_prefix = config["network_overrides"]["config"][config["selected_network"]]["address_prefix"]
    summaries_response = await wallet_client.get_wallets()
    wallet_id_passed_in = args.get("id", None)
    if wallet_id_passed_in is not None:
        for summary in summaries_response:
            typ = WalletType(int(summary["type"]))
            if summary["id"] == wallet_id_passed_in and typ != WalletType.POOLING_WALLET:
                print(f"Wallet with id: {wallet_id_passed_in} is not a pooling wallet. Please provide a different id.")
                return
        response: PoolWalletInfo = await wallet_client.pw_status(wallet_id_passed_in)

        pprint_pool_wallet_state(response, address_prefix)
    else:
        print(f"Wallet height: {await wallet_client.get_height_info()}")
        print(f"Sync status: {'Synced' if (await wallet_client.get_synced()) else 'Not synced'}")
        for summary in summaries_response:
            wallet_id = summary["id"]
            typ = WalletType(int(summary["type"]))
            if typ == WalletType.POOLING_WALLET:
                print(f"Wallet id {wallet_id}: ")
                response: PoolWalletInfo = await wallet_client.pw_status(wallet_id)
                pprint_pool_wallet_state(response, address_prefix)
                print("")