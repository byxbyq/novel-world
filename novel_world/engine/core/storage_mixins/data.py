"""存档数据结构"""
import json
from typing import Dict, Optional
from datetime import datetime

from .crypto import SaveCrypto


class SaveData:
    """存档数据结构"""
    
    def __init__(self, data: Dict, crypto: Optional[SaveCrypto] = None):
        self.data = data
        self.crypto = crypto
        self.signature = ""
        self.checksum = ""
        self.encrypted = False
        self.version = "1.0"
        self.timestamp = datetime.now().isoformat()
    
    def to_json(self) -> str:
        """序列化为JSON"""
        return json.dumps(self.data, ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str, crypto: Optional[SaveCrypto] = None) -> 'SaveData':
        """从JSON反序列化"""
        data = json.loads(json_str)
        return cls(data, crypto)
    
    def seal(self, encrypt: bool = False) -> Dict[str, any]:
        """
        封存数据（签名/加密）
        
        Args:
            encrypt: 是否加密
        
        Returns:
            封存后的数据包
        """
        json_data = self.to_json()
        
        if encrypt and self.crypto and self.crypto.is_encryption_available():
            # 加密
            encrypted_data = self.crypto.encrypt(json_data)
            self.encrypted = True
            
            # 计算加密数据的校验和
            self.checksum = self.crypto.compute_checksum(encrypted_data)
            
            # 签名
            self.signature = self.crypto.sign(encrypted_data + self.checksum)
            
            return {
                "version": self.version,
                "timestamp": self.timestamp,
                "encrypted": True,
                "checksum": self.checksum,
                "signature": self.signature,
                "data": encrypted_data,
            }
        else:
            # 不加密，只签名
            self.encrypted = False
            self.checksum = self.crypto.compute_checksum(json_data) if self.crypto else ""
            self.signature = self.crypto.sign(json_data + self.checksum) if self.crypto else ""
            
            return {
                "version": self.version,
                "timestamp": self.timestamp,
                "encrypted": False,
                "checksum": self.checksum,
                "signature": self.signature,
                "data": self.data,
            }
    
    @classmethod
    def unseal(cls, sealed_data: Dict, crypto: Optional[SaveCrypto] = None, verify: bool = True) -> 'SaveData':
        """
        解封数据（验证/解密）
        
        Args:
            sealed_data: 封存的数据包
            crypto: 加密工具
            verify: 是否验证签名
        
        Returns:
            解封后的存档数据
        
        Raises:
            ValueError: 验证失败时抛出
        """
        version = sealed_data.get("version", "1.0")
        timestamp = sealed_data.get("timestamp", "")
        encrypted = sealed_data.get("encrypted", False)
        checksum = sealed_data.get("checksum", "")
        signature = sealed_data.get("signature", "")
        data = sealed_data.get("data")
        
        # 验证签名
        if verify and crypto and signature:
            if encrypted:
                verify_data = str(data) + checksum
            else:
                verify_data = json.dumps(data, ensure_ascii=False) + checksum
            
            if not crypto.verify(verify_data, signature):
                raise ValueError("存档签名验证失败，存档可能被篡改！")
        
        # 验证校验和
        if verify and crypto and checksum:
            if encrypted:
                computed = crypto.compute_checksum(str(data))
            else:
                computed = crypto.compute_checksum(json.dumps(data, ensure_ascii=False))
            
            if computed != checksum:
                raise ValueError("存档校验和不匹配，数据可能损坏！")
        
        # 解密
        if encrypted and crypto:
            json_data = crypto.decrypt(data)
            save_data = cls.from_json(json_data, crypto)
        else:
            save_data = cls(data, crypto)
        
        save_data.version = version
        save_data.timestamp = timestamp
        save_data.encrypted = encrypted
        save_data.checksum = checksum
        save_data.signature = signature
        
        return save_data
