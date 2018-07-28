"""Use PaKeT smart contract."""
import os

import requests
import stellar_base.address
import stellar_base.asset
import stellar_base.builder
import stellar_base.keypair

import util.conversion
import util.logger

LOGGER = util.logger.logging.getLogger('pkt.paket')
DEBUG = bool(os.environ.get('PAKET_DEBUG'))
BUL_TOKEN_CODE = 'BUL'
ISSUER = os.environ['PAKET_USER_ISSUER']
ISSUER_SEED = os.environ.get('PAKET_SEED_ISSUER')
HORIZON = os.environ['PAKET_HORIZON_SERVER']


class StellarTransactionFailed(Exception):
    """A stellar transaction failed."""


class TrustError(Exception):
    """A stellar account does not trust asset"""


def get_keypair(pubkey=None, seed=None):
    """Get a keypair from pubkey or seed (default to random) with a decent string representation."""
    if pubkey is None:
        if seed is None:
            keypair = stellar_base.keypair.Keypair.random()
        else:
            keypair = stellar_base.keypair.Keypair.from_seed(seed)
        keypair.__class__ = type('DisplayUnlockedKeypair', (stellar_base.keypair.Keypair,), {
            '__repr__': lambda self: "KeyPair {} ({})".format(self.address(), self.seed())})
    else:
        keypair = stellar_base.keypair.Keypair.from_address(pubkey)
        keypair.__class__ = type('DisplayKeypair', (stellar_base.keypair.Keypair,), {
            '__repr__': lambda self: "KeyPair ({})".format(self.address())})
    return keypair


def get_bul_account(pubkey, accept_untrusted=False):
    """Get account details."""
    LOGGER.debug("getting details of %s", pubkey)
    try:
        details = stellar_base.address.Address(pubkey, horizon=HORIZON)
        details.get()
    except stellar_base.address.AccountNotExistError:
        raise stellar_base.address.AccountNotExistError("no account found for {}".format(pubkey))
    account = {'sequence': details.sequence, 'signers': details.signers, 'thresholds': details.thresholds}
    for balance in details.balances:
        if balance.get('asset_type') == 'native':
            account['xlm_balance'] = util.conversion.units_to_stroops(balance['balance'])
        if balance.get('asset_code') == BUL_TOKEN_CODE and balance.get('asset_issuer') == ISSUER:
            account['bul_balance'] = util.conversion.units_to_stroops(balance['balance'])
            account['bul_limit'] = util.conversion.units_to_stroops(balance['limit'])
    if 'bul_balance' not in account and not accept_untrusted:
        raise TrustError("account {} does not trust {} from {}".format(pubkey, BUL_TOKEN_CODE, ISSUER))
    return account


def add_memo(builder, memo):
    """Add a memo with limited length."""
    max_byte_length = 28
    if len(memo) > max_byte_length:
        LOGGER.warning("memo too long (%s > 28), truncating", len(memo))
        memo = memo[:max_byte_length]
    builder.add_text_memo(memo)
    return builder


def gen_builder(pubkey='', sequence_delta=None):
    """Create a builder."""
    if sequence_delta:
        sequence = int(get_bul_account(pubkey, accept_untrusted=True)['sequence']) + sequence_delta
        builder = stellar_base.builder.Builder(horizon=HORIZON, address=pubkey, sequence=sequence)
    else:
        builder = stellar_base.builder.Builder(horizon=HORIZON, address=pubkey)
    return builder


def submit(builder):
    """Submit a transaction and raise an exception if it fails."""
    response = builder.submit()
    if 'status' in response and response['status'] >= 300:
        raise StellarTransactionFailed(response)
    return response


def submit_transaction_envelope(envelope, seed=None):
    """Submit a transaction from an XDR of the envelope. Optionally sign it."""
    builder = stellar_base.builder.Builder(horizon=HORIZON, address='', secret=seed)
    builder.import_from_xdr(envelope)
    if seed:
        builder.sign()
    return submit(builder)


def prepare_create_account(from_pubkey, new_pubkey, starting_stroop_balance=50000000):
    """Prepare account creation transaction."""
    starting_xlm_balance = util.conversion.stroops_to_units(starting_stroop_balance)
    builder = gen_builder(from_pubkey)
    builder.append_create_account_op(destination=new_pubkey, starting_balance=starting_xlm_balance)
    return builder.gen_te().xdr().decode()


def prepare_trust(from_pubkey, stroop_limit=None):
    """Prepare trust transaction from account."""
    asset_limit = util.conversion.stroops_to_units(stroop_limit) if stroop_limit is not None else None
    builder = gen_builder(from_pubkey)
    builder.append_trust_op(ISSUER, BUL_TOKEN_CODE, asset_limit)
    return builder.gen_te().xdr().decode()


def prepare_send(from_pubkey, to_pubkey, stroop_amount, asset_code='XLM', asset_issuer=None):
    """Prepare asset transfer."""
    amount_to_send = util.conversion.stroops_to_units(stroop_amount)
    builder = gen_builder(from_pubkey)
    builder.append_payment_op(to_pubkey, amount_to_send, asset_code, asset_issuer)
    return builder.gen_te().xdr().decode()


def prepare_send_buls(from_pubkey, to_pubkey, stroop_amount):
    """Prepare BUL transfer."""
    return prepare_send(from_pubkey, to_pubkey, stroop_amount, BUL_TOKEN_CODE, ISSUER)


def prepare_send_lumens(from_pubkey, to_pubkey, stroop_amount):
    """Prepare XLM transfer."""
    return prepare_send(from_pubkey, to_pubkey, stroop_amount)


# pylint: disable=too-many-arguments
def prepare_escrow(
        escrow_pubkey, launcher_pubkey, courier_pubkey, recipient_pubkey, payment, collateral, deadline):
    """Prepare escrow transactions."""
    total = util.conversion.stroops_to_units(payment + collateral)

    # Refund transaction, in case of failed delivery, timelocked.
    builder = gen_builder(escrow_pubkey, sequence_delta=1)
    builder.append_payment_op(launcher_pubkey, total, BUL_TOKEN_CODE, ISSUER)
    builder.add_time_bounds(type('TimeBound', (), {'minTime': deadline, 'maxTime': 0})())
    add_memo(builder, 'refund')
    refund_envelope = builder.gen_te()

    # Payment transaction, in case of successful delivery, requires recipient signature.
    builder = gen_builder(escrow_pubkey, sequence_delta=1)
    builder.append_payment_op(courier_pubkey, total, BUL_TOKEN_CODE, ISSUER)
    add_memo(builder, 'payment')
    payment_envelope = builder.gen_te()

    # Merge transaction, to drain the remaining XLM from the account, timelocked.
    builder = gen_builder(escrow_pubkey, sequence_delta=2)
    builder.append_trust_op(ISSUER, BUL_TOKEN_CODE, 0)
    builder.append_account_merge_op(launcher_pubkey)
    add_memo(builder, 'close account')
    merge_envelope = builder.gen_te()

    # Set transactions and recipient as only signers.
    builder = gen_builder(escrow_pubkey)
    builder.append_set_options_op(
        signer_address=refund_envelope.hash_meta(),
        signer_type='preAuthTx',
        signer_weight=2)
    builder.append_set_options_op(
        signer_address=payment_envelope.hash_meta(),
        signer_type='preAuthTx',
        signer_weight=1)
    builder.append_set_options_op(
        signer_address=merge_envelope.hash_meta(),
        signer_type='preAuthTx',
        signer_weight=3)
    builder.append_set_options_op(
        signer_address=recipient_pubkey,
        signer_type='ed25519PublicKey',
        signer_weight=1)
    builder.append_set_options_op(
        master_weight=0, low_threshold=1, med_threshold=2, high_threshold=3)
    add_memo(builder, 'freeze')
    set_options_envelope = builder.gen_te()

    package_details = dict(
        escrow_pubkey=escrow_pubkey, launcher_pubkey=launcher_pubkey, recipient_pubkey=recipient_pubkey,
        payment=payment, collateral=collateral, deadline=deadline,
        set_options_transaction=set_options_envelope.xdr().decode(),
        refund_transaction=refund_envelope.xdr().decode(),
        payment_transaction=payment_envelope.xdr().decode(),
        merge_transaction=merge_envelope.xdr().decode())
    return package_details
# pylint: enable=too-many-arguments


# Debug methods.


def new_account(pubkey):
    """Create a new account and fund it with lumens. Debug only."""
    if not DEBUG:
        raise AssertionError('creating new account and funding it allowed only in debug mode')
    LOGGER.warning("creating and funding account %s", pubkey)
    request = requests.get("https://friendbot.stellar.org/?addr={}".format(pubkey))
    if request.status_code != 200:
        LOGGER.error("Request to friendbot failed: %s", request.json())
        raise StellarTransactionFailed("unable to create account {}".format(pubkey))


def fund_from_issuer(pubkey, stroop_amount):
    """Fund an account directly from issuer. Debug only."""
    if not DEBUG:
        raise AssertionError('funding allowed only in debug mode')
    bul_amount = util.conversion.stroops_to_units(stroop_amount)
    LOGGER.warning("funding %s from issuer", pubkey)
    builder = stellar_base.builder.Builder(horizon=HORIZON, secret=ISSUER_SEED)
    builder.append_payment_op(pubkey, bul_amount, BUL_TOKEN_CODE, ISSUER)
    add_memo(builder, 'fund')
    builder.sign()
    return submit(builder)
