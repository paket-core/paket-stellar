"""Tests for paket module"""
import unittest


import paket_stellar


class BasePaketTest(unittest.TestCase):
    """Base class for all paket tests"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.funded_seed = 'SDJGBJZMQ7Z4W3KMSMO2HYEV56DJPOZ7XRR7LJ5X2KW6VKBSLELR7MRQ'
        self.funded_pubkey = 'GBTWWXA3CDQOSRQ3645B2L4A345CRSKSV6MSBUO4LSHC26ZMNOYFN2YJ'
        self.valid_untrusted_pubkey = 'GBPRNQA4HU72SJH2ZR3GV4AYCPJEDS64JSA4A62IUW7SYVUKICXXNGWZ'
        self.invalid_seed = 'GJ1FN8WWJ6FJSS4SKWO5QiJKH'
        self.invalid_pubkey = 'PGJRLVAEMVWKDSNVSK3FD2LV8DS4FJD6'


class TestGetKeypair(BasePaketTest):
    """Tests for get_keypair function"""

    def test_get_from_seed(self):
        """Test for getting keypair from seed"""
        keypair = paket_stellar.get_keypair(seed=self.funded_seed)
        self.assertEqual(keypair.address().decode(), self.funded_pubkey)

    def test_get_from_pubkey(self):
        """Test for getting keypair from pubkey"""
        keypair = paket_stellar.get_keypair(pubkey=self.funded_pubkey)
        self.assertIsNone(keypair.signing_key)

    def test_get_random(self):
        """Test for getting random keypair"""
        keypair = paket_stellar.get_keypair()
        self.assertIsNotNone(keypair.signing_key)
        self.assertIsNotNone(keypair.address())

    def test_get_from_invalid_seed(self):
        """Test for getting keypair from invalid seed"""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.DecodeError):
            paket_stellar.get_keypair(seed=self.invalid_seed)

    def test_get_from_invalid_pubkey(self):
        """Test for getting from invalid pubkey"""
        with self.assertRaises(paket_stellar.stellar_base.exceptions.DecodeError):
            paket_stellar.get_keypair(pubkey=self.invalid_pubkey)


class TestGetBulAccount(BasePaketTest):
    """Tests for get_bul_account function"""

    def test_get_bul_account(self):
        """Test for getting bul account"""
        account = paket_stellar.get_bul_account(pubkey=self.funded_pubkey)
        self.assertIn('bul_balance', account)

    def test_accept_untrusted(self):
        """Test for getting bul account that actualy may not have bul balance"""
        account = paket_stellar.get_bul_account(self.valid_untrusted_pubkey, accept_untrusted=True)
        self.assertNotIn('bul_balance', account)
        with self.assertRaises(AssertionError):
            paket_stellar.get_bul_account(self.valid_untrusted_pubkey)

    def test_invalid_pubkey(self):
        """Test for getting bul account from invalid pubkey"""
        with self.assertRaises(AssertionError):
            paket_stellar.get_bul_account(self.invalid_pubkey)


class TestAddMemo(BasePaketTest):
    """Tests for adding memo"""

    def test_long_memo(self):
        """Test for adding memo with length greater than 28 bytes"""
        memo = 'This is very long text that will be truncated to 28 bytes length'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.funded_seed)
        builder = paket_stellar.add_memo(builder, memo)
        memo_length = len(builder.memo.text)
        self.assertGreater(memo_length, 0)
        self.assertLessEqual(memo_length, 28)

    def test_short_memo(self):
        """Test for adding memo with length less or equal than 28 bytes"""
        memo = 'This is short text of 28 len'
        builder = paket_stellar.stellar_base.builder.Builder(secret=self.funded_seed)
        builder = paket_stellar.add_memo(builder, memo)
        self.assertEqual(builder.memo.text, memo.encode('utf-8'))


class TestSubmit(BasePaketTest):
    """Tests for submit function"""

    def test_submit(self):
        """Test submitting properly created and signed transaction"""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        builder = paket_stellar.gen_builder(pubkey=self.funded_pubkey)
        builder.append_create_account_op(destination=pubkey, starting_balance=5)
        builder.sign(secret=self.funded_seed)
        result = paket_stellar.submit(builder)
        self.assertIn('result_xdr', result)
        self.assertEqual(result['result_xdr'], 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAA=')

    def test_submit_anauth(self):
        """Test submitting unsigned transaction"""
        new_keypair = paket_stellar.get_keypair()
        pubkey = new_keypair.address().decode()
        builder = paket_stellar.gen_builder(pubkey=self.funded_pubkey)
        builder.append_create_account_op(destination=pubkey, starting_balance=5)
        with self.assertRaises(paket_stellar.StellarTransactionFailed):
            paket_stellar.submit(builder)
