"""云存储接口和云端存档管理"""
import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# SAVE_DIR 引用会从父模块传入
_SAVE_DIR = None

def _get_save_dir():
    global _SAVE_DIR
    if _SAVE_DIR is None:
        from pathlib import Path
        _SAVE_DIR = Path(r"H:\\baichengzhu\\game\\saves")
    return _SAVE_DIR


class CloudStorageProvider(ABC):
    """云存储提供者接口"""
    
    @abstractmethod
    def upload(self, key: str, data: bytes) -> bool:
        """上传数据"""
        pass
    
    @abstractmethod
    def download(self, key: str) -> Optional[bytes]:
        """下载数据"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除数据"""
        pass
    
    @abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """列出所有键"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查是否存在"""
        pass


class HttpApiCloudStorage(CloudStorageProvider):
    """
    HTTP API 云存储实现
    
    通过自定义HTTP API对接云存储服务
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str = None,
        upload_endpoint: str = "/upload",
        download_endpoint: str = "/download",
        delete_endpoint: str = "/delete",
        list_endpoint: str = "/list",
        headers: Dict[str, str] = None,
        timeout: int = 30
    ):
        """
        初始化HTTP API云存储
        
        Args:
            base_url: API基础URL
            api_key: API密钥
            upload_endpoint: 上传端点
            download_endpoint: 下载端点
            delete_endpoint: 删除端点
            list_endpoint: 列表端点
            headers: 额外请求头
            timeout: 请求超时
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.upload_endpoint = upload_endpoint
        self.download_endpoint = download_endpoint
        self.delete_endpoint = delete_endpoint
        self.list_endpoint = list_endpoint
        self.timeout = timeout
        
        # 默认请求头
        self.headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
        if headers:
            self.headers.update(headers)
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Tuple[int, Dict]:
        """发起HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if data:
                body = json.dumps(data).encode('utf-8')
            else:
                body = None
            
            req = urllib.request.Request(url, data=body, headers=self.headers, method=method)
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        
        except urllib.error.HTTPError as e:
            return e.code, {"error": str(e)}
        except Exception as e:
            return 0, {"error": str(e)}
    
    def upload(self, key: str, data: bytes) -> bool:
        """上传数据"""
        import base64
        
        # Base64编码数据
        encoded = base64.b64encode(data).decode('ascii')
        
        status, response = self._make_request("POST", self.upload_endpoint, {
            "key": key,
            "data": encoded,
        })
        
        return status == 200
    
    def download(self, key: str) -> Optional[bytes]:
        """下载数据"""
        import base64
        
        status, response = self._make_request("GET", f"{self.download_endpoint}?key={key}")
        
        if status == 200 and "data" in response:
            try:
                return base64.b64decode(response["data"])
            except:
                return None
        
        return None
    
    def delete(self, key: str) -> bool:
        """删除数据"""
        status, _ = self._make_request("DELETE", f"{self.delete_endpoint}?key={key}")
        return status == 200
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """列出所有键"""
        status, response = self._make_request("GET", f"{self.list_endpoint}?prefix={prefix}")
        
        if status == 200 and "keys" in response:
            return response["keys"]
        
        return []
    
    def exists(self, key: str) -> bool:
        """检查是否存在"""
        keys = self.list_keys(key)
        return key in keys


class SimpleHttpCloudStorage(CloudStorageProvider):
    """
    简单HTTP云存储
    
    直接通过PUT/GET请求操作文件
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str = None,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def upload(self, key: str, data: bytes) -> bool:
        """上传数据"""
        url = f"{self.base_url}/{key}"
        
        try:
            req = urllib.request.Request(url, data=data, headers=self._get_headers(), method='PUT')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
    
    def download(self, key: str) -> Optional[bytes]:
        """下载数据"""
        url = f"{self.base_url}/{key}"
        
        try:
            req = urllib.request.Request(url, headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """删除数据"""
        url = f"{self.base_url}/{key}"
        
        try:
            req = urllib.request.Request(url, headers=self._get_headers(), method='DELETE')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """列出所有键"""
        url = f"{self.base_url}/?list=1&prefix={prefix}"
        
        try:
            req = urllib.request.Request(url, headers=self._get_headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("keys", [])
        except Exception as e:
            logger.error(f"List failed: {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """检查是否存在"""
        url = f"{self.base_url}/{key}"
        
        try:
            req = urllib.request.Request(url, headers=self._get_headers(), method='HEAD')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status == 200
        except:
            return False


class CloudSaveManager:
    """
    云端存档管理器
    
    支持上传、下载、同步存档到云端
    """
    
    def __init__(
        self,
        storage: 'EnhancedGameStorage',
        cloud_provider: CloudStorageProvider,
        sync_enabled: bool = True
    ):
        """
        初始化云端存档管理器
        
        Args:
            storage: 本地存档管理器
            cloud_provider: 云存储提供者
            sync_enabled: 是否启用同步
        """
        self.storage = storage
        self.cloud = cloud_provider
        self.sync_enabled = sync_enabled
        
        # 同步状态
        self._sync_status: Dict[str, Dict] = {}
        self._last_sync: float = 0
    
    def upload_save(self, slot: int, world: Any, description: str = "") -> Tuple[bool, str]:
        """
        上传存档到云端
        
        Args:
            slot: 存档槽位
            world: 游戏世界
            description: 描述
        
        Returns:
            (成功, 消息)
        """
        try:
            SAVE_DIR = _get_save_dir()
            # 保存到本地
            metadata = self.storage.save_encrypted(world, slot, description)
            
            # 读取存档文件
            filepath = SAVE_DIR / f"save_slot_{slot}.json"
            if not filepath.exists():
                return False, "本地存档不存在"
            
            with open(filepath, 'rb') as f:
                data = f.read()
            
            # 上传到云端
            cloud_key = f"saves/slot_{slot}.json"
            if self.cloud.upload(cloud_key, data):
                # 上传元数据
                meta_key = f"saves/slot_{slot}_meta.json"
                meta_data = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
                self.cloud.upload(meta_key, meta_data)
                
                # 更新同步状态
                self._sync_status[str(slot)] = {
                    "last_upload": datetime.now().isoformat(),
                    "size": len(data),
                }
                
                logger.info(f"Save slot {slot} uploaded to cloud")
                return True, "上传成功"
            else:
                return False, "上传失败"
        
        except Exception as e:
            logger.error(f"Upload save failed: {e}")
            return False, f"上传失败: {e}"
    
    def download_save(self, slot: int) -> Tuple[bool, str]:
        """
        从云端下载存档
        
        Args:
            slot: 存档槽位
        
        Returns:
            (成功, 消息)
        """
        try:
            SAVE_DIR = _get_save_dir()
            cloud_key = f"saves/slot_{slot}.json"
            
            # 下载存档
            data = self.cloud.download(cloud_key)
            if data is None:
                return False, "云端存档不存在"
            
            # 保存到本地
            filepath = SAVE_DIR / f"save_slot_{slot}.json"
            with open(filepath, 'wb') as f:
                f.write(data)
            
            # 下载元数据
            meta_key = f"saves/slot_{slot}_meta.json"
            meta_data = self.cloud.download(meta_key)
            if meta_data:
                metadata = json.loads(meta_data.decode('utf-8'))
                # 更新本地元数据
                all_metadata = self.storage._load_all_metadata()
                all_metadata[str(slot)] = metadata
                self.storage._save_all_metadata(all_metadata)
            
            # 更新同步状态
            self._sync_status[str(slot)] = {
                "last_download": datetime.now().isoformat(),
                "size": len(data),
            }
            
            logger.info(f"Save slot {slot} downloaded from cloud")
            return True, "下载成功"
        
        except Exception as e:
            logger.error(f"Download save failed: {e}")
            return False, f"下载失败: {e}"
    
    def sync_save(self, slot: int, direction: str = "both") -> Tuple[bool, str]:
        """
        同步存档
        
        Args:
            slot: 存档槽位
            direction: 同步方向 (upload, download, both)
        
        Returns:
            (成功, 消息)
        """
        SAVE_DIR = _get_save_dir()
        if direction == "upload":
            # 只上传
            filepath = SAVE_DIR / f"save_slot_{slot}.json"
            if not filepath.exists():
                return False, "本地存档不存在"
            
            with open(filepath, 'rb') as f:
                data = f.read()
            
            cloud_key = f"saves/slot_{slot}.json"
            if self.cloud.upload(cloud_key, data):
                return True, "上传成功"
            else:
                return False, "上传失败"
        
        elif direction == "download":
            # 只下载
            return self.download_save(slot)
        
        else:  # both
            # 双向同步：比较时间戳，保留较新的
            local_path = SAVE_DIR / f"save_slot_{slot}.json"
            cloud_key = f"saves/slot_{slot}.json"
            
            local_exists = local_path.exists()
            cloud_exists = self.cloud.exists(cloud_key)
            
            if not local_exists and not cloud_exists:
                return False, "存档不存在"
            
            if local_exists and not cloud_exists:
                # 只有本地，上传
                with open(local_path, 'rb') as f:
                    data = f.read()
                if self.cloud.upload(cloud_key, data):
                    return True, "已上传到云端"
                else:
                    return False, "上传失败"
            
            if not local_exists and cloud_exists:
                # 只有云端，下载
                return self.download_save(slot)
            
            # 都存在，比较时间
            local_mtime = local_path.stat().st_mtime
            
            # 获取云端元数据
            meta_key = f"saves/slot_{slot}_meta.json"
            meta_data = self.cloud.download(meta_key)
            
            if meta_data:
                metadata = json.loads(meta_data.decode('utf-8'))
                cloud_time = datetime.fromisoformat(metadata.get("timestamp", "1970-01-01")).timestamp()
                
                if local_mtime > cloud_time:
                    # 本地较新，上传
                    with open(local_path, 'rb') as f:
                        data = f.read()
                    if self.cloud.upload(cloud_key, data):
                        return True, "本地较新，已同步到云端"
                    else:
                        return False, "上传失败"
                else:
                    # 云端较新，下载
                    success, msg = self.download_save(slot)
                    if success:
                        return True, "云端较新，已同步到本地"
                    else:
                        return False, msg
            else:
                # 无法比较，默认下载
                return self.download_save(slot)
    
    def list_cloud_saves(self) -> List[Dict]:
        """列出云端存档"""
        keys = self.cloud.list_keys("saves/")
        
        saves = []
        for key in keys:
            if key.endswith('.json') and not key.endswith('_meta.json'):
                slot_str = key.replace('saves/slot_', '').replace('.json', '')
                try:
                    slot = int(slot_str)
                    
                    # 获取元数据
                    meta_key = f"saves/slot_{slot}_meta.json"
                    meta_data = self.cloud.download(meta_key)
                    
                    if meta_data:
                        metadata = json.loads(meta_data.decode('utf-8'))
                    else:
                        metadata = {}
                    
                    saves.append({
                        "slot": slot,
                        "exists": True,
                        "metadata": metadata,
                        "cloud_key": key,
                    })
                except:
                    pass
        
        return sorted(saves, key=lambda x: x["slot"])
    
    def delete_cloud_save(self, slot: int) -> bool:
        """删除云端存档"""
        cloud_key = f"saves/slot_{slot}.json"
        meta_key = f"saves/slot_{slot}_meta.json"
        
        success = True
        if not self.cloud.delete(cloud_key):
            success = False
        if not self.cloud.delete(meta_key):
            success = False
        
        if success:
            logger.info(f"Cloud save slot {slot} deleted")
        
        return success
    
    def get_sync_status(self, slot: int = None) -> Dict:
        """获取同步状态"""
        if slot is not None:
            return self._sync_status.get(str(slot), {})
        return self._sync_status.copy()
    
    def auto_sync_all(self, direction: str = "both") -> Dict[int, Tuple[bool, str]]:
        """
        自动同步所有存档
        
        Args:
            direction: 同步方向
        
        Returns:
            {槽位: (成功, 消息)}
        """
        results = {}
        
        for slot in range(6):  # 0-5
            try:
                results[slot] = self.sync_save(slot, direction)
            except Exception as e:
                results[slot] = (False, str(e))
        
        self._last_sync = time.time()
        return results


# ============================================================
# 云端存档便捷函数
# ============================================================
def create_http_cloud_storage(
    base_url: str,
    api_key: str = None,
    style: str = "simple"  # simple 或 api
) -> CloudStorageProvider:
    """
    创建HTTP云存储
    
    Args:
        base_url: API基础URL
        api_key: API密钥
        style: 风格 (simple 或 api)
    
    Returns:
        云存储提供者
    """
    if style == "api":
        return HttpApiCloudStorage(base_url, api_key)
    else:
        return SimpleHttpCloudStorage(base_url, api_key)


def create_cloud_save_manager(
    base_url: str,
    api_key: str = None,
    encryption_key: str = None
) -> CloudSaveManager:
    """
    创建云端存档管理器
    
    Args:
        base_url: 云存储API URL
        api_key: 云存储API密钥
        encryption_key: 存档加密密钥
    
    Returns:
        云端存档管理器
    """
    from ..storage import get_enhanced_storage
    
    storage = get_enhanced_storage(encryption_key)
    cloud = create_http_cloud_storage(base_url, api_key)
    
    return CloudSaveManager(storage, cloud)
