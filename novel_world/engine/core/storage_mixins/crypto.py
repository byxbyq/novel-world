"""加密和签名工具"""
import os
import hashlib
import hmac
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SaveCrypto:
    """存档加密和签名工具"""
    
    def __init__(self, encryption_key: Optional[str] = None, signing_key: Optional[str] = None):
        """
        初始化加密工具
        
        Args:
            encryption_key: 加密密钥（None则自动生成）
            signing_key: 签名密钥（None则自动生成）
        """
        self._cipher = None
        self._encryption_key = None
        self._signing_key = None
        
        # 初始化加密
        if encryption_key:
            self._init_encryption(encryption_key)
        
        # 初始化签名
        if signing_key:
            self._signing_key = signing_key.encode('utf-8')
        else:
            # 生成默认签名密钥
            self._signing_key = hashlib.sha256(b"save_signing_key_default").digest()
    
    def _init_encryption(self, key: str):
        """初始化AES加密"""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import padding
            
            # 派生密钥（确保32字节用于AES-256）
            derived_key = hashlib.sha256(key.encode('utf-8')).digest()
            
            self._encryption_key = derived_key
            self._cipher_available = True
            
        except ImportError:
            logger.warning("cryptography package not installed, encryption disabled")
            self._cipher_available = False
    
    def is_encryption_available(self) -> bool:
        """检查加密是否可用"""
        return getattr(self, '_cipher_available', False)
    
    def encrypt(self, data: str) -> str:
        """
        加密数据
        
        Args:
            data: 明文数据
        
        Returns:
            Base64编码的密文
        """
        if not self.is_encryption_available() or not self._encryption_key:
            return data
        
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import padding
            
            # 生成随机IV
            iv = os.urandom(16)
            
            # PKCS7填充
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
            
            # 加密
            cipher = Cipher(
                algorithms.AES(self._encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            
            # 返回 IV + 密文（Base64编码）
            return base64.b64encode(iv + ciphertext).decode('ascii')
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        解密数据
        
        Args:
            encrypted_data: Base64编码的密文
        
        Returns:
            明文数据
        """
        if not self.is_encryption_available() or not self._encryption_key:
            return encrypted_data
        
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import padding
            
            # Base64解码
            data = base64.b64decode(encrypted_data)
            
            # 提取IV和密文
            iv = data[:16]
            ciphertext = data[16:]
            
            # 解密
            cipher = Cipher(
                algorithms.AES(self._encryption_key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # 去除填充
            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded_data) + unpadder.finalize()
            
            return plaintext.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"解密失败: {e}")
    
    def sign(self, data: str) -> str:
        """
        对数据签名
        
        Args:
            data: 要签名的数据
        
        Returns:
            签名（十六进制）
        """
        return hmac.new(
            self._signing_key,
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def verify(self, data: str, signature: str) -> bool:
        """
        验证签名
        
        Args:
            data: 数据
            signature: 签名
        
        Returns:
            是否验证通过
        """
        expected = self.sign(data)
        return hmac.compare_digest(expected, signature)
    
    def compute_checksum(self, data: str) -> str:
        """
        计算数据校验和
        
        Args:
            data: 数据
        
        Returns:
            SHA256校验和（十六进制）
        """
        return hashlib.sha256(data.encode('utf-8')).hexdigest()
