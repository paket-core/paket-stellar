"""Tests for paket module."""
import unittest

import util.logger

import paket_stellar


util.logger.setup()

LOGGER = util.logger.logging.getLogger('pkt.paket_stellar.tests')
START_ACCOUNT_BALANCE = 1000000000
MINIMUM_ACCOUNT_BALANCE = 50000000

BUL_ACCOUNT_SEED = 'SC2HZK6TXU5GJ2BSADFZPIDM4EFSTLULY3WUMI2FPYI7F44PFVQPIO6Z'
REGULAR_ACCOUNT_SEED = 'SCQHHZ5DPDFN7IPOOLE47IWF6UUPJUPTP474FQCZA2UGXTZZ4J2O4PZY'
RELAY_SEED = 'SBV4FBXKQFAOS4TFGPL6AQDZLDYRLEPCM2IQCFOOWR77KHOG3RJB62KR'
SEED = 'SA6IIH3J3YTCEYBJ5ZMSCTLXUIHJOOKLOH6HVWCSB4HMERXQVI3M2YSP'


def setup_account(seed, new_account=False, add_trust=False):
    """Generate new keypair, and optionally create account and set trust."""
    keypair = paket_stellar.get_keypair(seed=seed)
    pubkey = keypair.address().decode()
    seed = keypair.seed().decode()

    if new_account:
        try:
            account = paket_stellar.get_bul_account(pubkey, accept_untrusted=True)
        except paket_stellar.stellar_base.address.AccountNotExistError:
            LOGGER.info("%s not exist and will be created", pubkey)
            create_account_transaction = paket_stellar.prepare_create_account(
                paket_stellar.ISSUER, pubkey, START_ACCOUNT_BALANCE)
            paket_stellar.submit_transaction_envelope(create_account_transaction, paket_stellar.ISSUER_SEED)
        else:
            LOGGER.info("%s already exist", pubkey)
            if account['xlm_balance'] < MINIMUM_ACCOUNT_BALANCE:
                LOGGER.info("%s has %s XLM on balance and need to be funded", pubkey, account['xlm_balance'])
                send_xlm_transaction = paket_stellar.prepare_send_lumens(
                    paket_stellar.ISSUER, pubkey, START_ACCOUNT_BALANCE)
                paket_stellar.submit_transaction_envelope(send_xlm_transaction, paket_stellar.ISSUER_SEED)
            else:
                LOGGER.info("%s has %s XLM on balance", pubkey, account['xlm_balance'])

    if new_account and add_trust:
        try:
            paket_stellar.get_bul_account(pubkey)
        except paket_stellar.TrustError:
            LOGGER.info("BUL trustline will be added to %s", pubkey)
            trust_transaction = paket_stellar.prepare_trust(pubkey)
            paket_stellar.submit_transaction_envelope(trust_transaction, seed)
        else:
            LOGGER.info("%s already trust BUL", pubkey)

    return pubkey, seed


# pylint: disable=too-many-instance-attributes
class BasePaketTest(unittest.TestCase):
    """Base class for all paket tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bul_account_pubkey, self.bul_account_seed = setup_account(
            BUL_ACCOUNT_SEED, new_account=True, add_trust=True)
        self.regular_account_pubkey, self.regular_account_seed = setup_account(
            REGULAR_ACCOUNT_SEED, new_account=True)
        self.pubkey, self.seed = setup_account(SEED)
        self.invalid_pubkey = 'invalid pubkey string'
        self.invalid_seed = 'invalid seed string'
# pylint: enable=too-many-instance-attributes


class TestGetKeypair(BasePaketTest):
    """Tests for get_keypair function."""

    def test_get_from_seed(self):
        """Test for getting keypair from seed."""
        keypair = paket_stellar.get_keypair(seed=self.seed)
        self.assertEqual(keypair.address().decode(), self.pubkey)

    def test_get_from_pubkey(self):
        """Test for getting keypair from pubkey."""
        keypair = paket_stellar.get_keypair(pubkey=self.pubkey)
        self.assertIsNone(keypair.signing_key)

    def test_get_random(self):
        """Test for getting random keypair."""
        keypair = paket_stellar.get_keypair()
        self.assertIsNotNone(keypair.signing_key)
        self.assertIsNotNone(keypair.address())

    def test_get_from_invalid_seed(self):
        """Test for getting keypair from invalid seed."""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.StellarSecretInvalidError):
            paket_stellar.get_keypair(seed=self.invalid_seed)

    def test_get_from_invalid_pubkey(self):
        """Test for getting from invalid pubkey."""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.StellarAddressInvalidError):
            paket_stellar.get_keypair(pubkey=self.invalid_pubkey)


class TestGetBulAccount(BasePaketTest):
    """Tests for get_bul_account function."""

    def test_get_bul_account(self):
        """Test for getting bul account."""
        account = paket_stellar.get_bul_account(pubkey=self.bul_account_pubkey)
        self.assertIn('bul_balance', account)

    def test_accept_untrusted(self):
        """Test for getting bul account that actualy may not have bul balance."""
        account = paket_stellar.get_bul_account(self.regular_account_pubkey, accept_untrusted=True)
        self.assertNotIn('bul_balance', account)
        with self.assertRaises(paket_stellar.TrustError):
            paket_stellar.get_bul_account(self.regular_account_pubkey)


class TestAddMemo(BasePaketTest):
    """Tests for adding memo."""

    def test_long_memo(self):
        """Test for adding memo with length greater than 28 bytes."""
        memo = 'This is very long text that will be truncated to 28 bytes length'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.regular_account_seed)
        builder = paket_stellar.add_memo(builder, memo)
        memo_length = len(builder.memo.text)
        self.assertGreater(memo_length, 0)
        self.assertLessEqual(memo_length, 28)

    def test_short_memo(self):
        """Test for adding memo with length less or equal than 28 bytes."""
        memo = 'This is short text of 28 len'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.regular_account_seed)
        builder = paket_stellar.add_memo(builder, memo)
        self.assertEqual(builder.memo.text, memo.encode('utf-8'))


class TestSubmit(BasePaketTest):
    """Tests for submit function."""

    def test_submit(self):
        """Test submitting properly created and signed transaction."""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        create_account_transaction = paket_stellar.prepare_create_account(
            self.regular_account_pubkey, pubkey, 50000000)
        result = paket_stellar.submit_transaction_envelope(create_account_transaction, self.regular_account_seed)
        self.assertIn('result_xdr', result)
        self.assertEqual(result['result_xdr'], 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAA=')

    def test_submit_anauth(self):
        """Test submitting unsigned transaction."""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        builder = paket_stellar.gen_builder(pubkey=self.regular_account_pubkey)
        builder.append_create_account_op(destination=pubkey, starting_balance='5')
        with self.assertRaises(paket_stellar.StellarTransactionFailed):
            paket_stellar.submit(builder)


class TestRelay(BasePaketTest):
    """Test for relay transactions."""

    def test_create_relay(self):
        """Test creating relay transactions."""

        relay_pubkey, _ = setup_account(RELAY_SEED, new_account=True, add_trust=True)
        relayer_keypair = paket_stellar.get_keypair()
        relayee_keypair = paket_stellar.get_keypair()

        relay_details = paket_stellar.prepare_relay(
            relay_pubkey, relayer_keypair.address().decode(),
            relayee_keypair.address().decode(), 100000000, 150000000, 1568455600)

        self.assertTrue(
            relay_details['set_options_transaction'] and
            relay_details['relay_transaction'] and
            relay_details['sequence_merge_transaction'] and
            relay_details['timelock_merge_transaction'])
