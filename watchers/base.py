"""
Base watcher class for price monitoring
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseWatcher(ABC):
    """Abstract base class for price watchers"""
    
    def __init__(self, name: str, url: str, threshold: float, config: Dict[str, Any]):
        """
        Initialize the watcher
        
        Args:
            name: Unique name for this watcher
            url: URL to monitor
            threshold: Price threshold (alert if price <= threshold)
            config: Additional configuration specific to the watcher type
        """
        self.name = name
        self.url = url
        self.threshold = threshold
        self.config = config
    
    @abstractmethod
    def fetch_price(self) -> Optional[float]:
        """
        Fetch the current price from the website
        
        Returns:
            Current price as float, or None if extraction fails
        """
        pass
    
    @abstractmethod
    def format_alert_message(self, price: float) -> str:
        """
        Format the alert message to send
        
        Args:
            price: The price that triggered the alert
            
        Returns:
            Formatted message string
        """
        pass
    
    def check_price(self) -> Optional[Dict[str, Any]]:
        """
        Check if price is below threshold
        
        Returns:
            Dict with 'price' and 'message' if alert should be sent, None otherwise
        """
        price = self.fetch_price()
        
        if price is None:
            print(f"[{self.name}] Failed to fetch price")
            return None
        
        print(f"[{self.name}] Current price: {price}€, Threshold: {self.threshold}€")
        
        if price <= self.threshold:
            message = self.format_alert_message(price)
            return {
                'price': price,
                'message': message,
                'url': self.url
            }
        
        return None

