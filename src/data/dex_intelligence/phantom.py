import json
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def parse_nextjs_serialized_data(serialized_str: str) -> Any:
    """
    Parse Next.js serialized data format.
    
    Next.js uses a special serialization format where:
    - Dates are represented as $D{ISO_STRING}
    - Undefined values are represented as $undefined
    - Other special values may exist
    
    This function converts $D{ISO_STRING} to proper datetime objects.
    
    Args:
        serialized_str: The serialized string from Next.js
        
    Returns:
        Parsed Python object with dates converted to datetime objects
    """
    try:
        # First parse as JSON to get the basic structure
        data = json.loads(serialized_str)
        
        # Recursively walk through the data to find and convert $D date strings
        def convert_dates(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, str) and value.startswith('$D'):
                        # Try to parse the date string
                        date_str = value[2:]  # Remove the $D prefix
                        try:
                            # Normalize the date string for parsing
                            normalized = date_str
                            if normalized.endswith('Z'):
                                normalized = normalized[:-1] + '+00:00'
                            elif '+' not in normalized and '-' not in normalized[-6:]:
                                # No timezone info, assume UTC
                                normalized += '+00:00'
                            obj[key] = datetime.fromisoformat(normalized)
                        except Exception as e:
                            logger.warning(f"Failed to parse Next.js date '{date_str}': {e}")
                            # Keep the original string if parsing fails
                    else:
                        # Recursively process nested structures
                        convert_dates(value)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if isinstance(item, str) and item.startswith('$D'):
                        # Try to parse the date string
                        date_str = item[2:]  # Remove the $D prefix
                        try:
                            # Normalize the date string for parsing
                            normalized = date_str
                            if normalized.endswith('Z'):
                                normalized = normalized[:-1] + '+00:00'
                            elif '+' not in normalized and '-' not in normalized[-6:]:
                                # No timezone info, assume UTC
                                normalized += '+00:00'
                            obj[i] = datetime.fromisoformat(normalized)
                        except Exception as e:
                            logger.warning(f"Failed to parse Next.js date '{date_str}': {e}")
                            # Keep the original string if parsing fails
                    else:
                        # Recursively process nested structures
                        convert_dates(item)
            # For other types (str, int, float, bool, None), do nothing
        
        # Apply the conversion
        convert_dates(data)
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.debug(f"String to parse: {serialized_str[:500]}...")
        # If we can't parse as JSON, return the original string
        return serialized_str

class PhantomLauncherScanner:
    """
    Scanner for Phantom.com token launches.
    
    Phantom.com appears to launch tokens similar to PumpFun but with different 
    metadata structure. This scanner fetches and parses the launch data.
    """
    
    def __init__(self):
        self.launch_url = 'https://trade.phantom.com/launches'
    
    def fetch_launch_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch raw launch data from Phantom.com.
        
        Returns:
            Raw response data or None if failed
        """
        try:
            import httpx
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            with httpx.Client(timeout=15.0) as client:
                response = client.get(self.launch_url, headers=headers)
                response.raise_for_status()
                return response.text
                
        except Exception as e:
            logger.error(f"Failed to fetch Phantom.com launch data: {e}")
            return None
    
    def parse_launch_data(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse Phantom.com launch data from HTML content.
        
        Args:
            html_content: Raw HTML from Phantom.com launches page
            
        Returns:
            List of token dictionaries in standardized format
        """
        tokens = []
        
        try:
            # Extract script tags that might contain initialData
            script_pattern = r'<script[^>]*>(.*?)</script>'
            scripts = re.findall(script_pattern, html_content, re.DOTALL)
            
            for script_content in scripts:
                if 'initialData' in script_content and 'NEW' in script_content:
                    logger.info("Found Phantom.com initialData in script tag")
                    
                    # Extract the initialData portion
                    # Look for the pattern: initialData":"{...} or initialData': '{...}
                    # Based on the user's data, it appears to be: initialData":{
                    
                    # Try to find the JSON data
                    # Match initialData: { ... } or initialData": { ... } etc.
                    json_pattern = r'initialData["\']?\s*:\s*["\']?\s*({.*?})\s*}}'
                    json_match = re.search(json_pattern, script_content, re.DOTALL)
                    
                    if json_match:
                        json_str = json_match.group(1)
                        logger.debug(f"Extracted JSON string: {json_str[:200]}...")
                        
                        # Parse the Next.js serialized data
                        parsed_data = parse_nextjs_serialized_data(json_str)
                        
                        if isinstance(parsed_data, dict) and 'NEW' in parsed_data:
                            new_tokens = parsed_data['NEW']
                            logger.info(f"Found {len(new_tokens)} new tokens from Phantom.com")
                            
                            # Convert to standardized format
                            for token_data in new_tokens:
                                standardized_token = self._standardize_token(token_data)
                                if standardized_token:
                                    tokens.append(standardized_token)
                        else:
                            logger.warning("Parsed data doesn't contain expected 'NEW' field")
                    else:
                        logger.warning("Could not extract JSON from initialData")
                    break  # We found what we needed, no need to check other scripts
                    
        except Exception as e:
            logger.error(f"Error parsing Phantom.com launch data: {e}")
        
        return tokens
    
    def _standardize_token(self, token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert Phantom.com token data to standardized format.
        
        Args:
            token_data: Raw token data from Phantom.com
            
        Returns:
            Standardized token dictionary or None if invalid
        """
        try:
            # Extract basic token info
            token_address = token_data.get('tokenAddress')
            if not token_address:
                logger.warning("Token missing address")
                return None
            
            # Parse creation time if available
            created_at = None
            token_created_at = token_data.get('tokenCreatedAt')
            if token_created_at and isinstance(token_created_at, str):
                # Remove the $D prefix if present
                if token_created_at.startswith('$D'):
                    token_created_at = token_created_at[2:]
                try:
                    if token_created_at.endswith('Z'):
                        token_created_at = token_created_at[:-1] + '+00:00'
                    elif '+' not in token_created_at and '-' not in token_created_at[-6:]:
                        token_created_at += '+00:00'
                    created_at = datetime.fromisoformat(token_created_at)
                except Exception as e:
                    logger.debug(f"Could not parse token creation time '{token_created_at}': {e}")
            
            # Standardized format matching other dex intelligence providers
            standardized = {
                'tokenAddress': token_address,
                'symbol': token_data.get('symbol', ''),
                'name': token_data.get('name', ''),
                'marketCap': float(token_data.get('marketCap', 0)),
                'liquidity': float(token_data.get('liquidity', 0)),
                'volume24h': float(token_data.get('volume', 0)),
                'priceChange24h': 0.0,  # Not provided in this data
                'holders': int(token_data.get('uniqueHolders', 0)),
                'createdAt': created_at,
                'bondingCurve': token_data.get('bondingCurve', ''),
                'bondingCurvePlatform': token_data.get('bondingCurvePlatform', ''),
                'devHolding': float(token_data.get('devHolding', 0)),
                'snipersHolding': float(token_data.get('snipersHolding', 0)),
                'bundlersHolding': float(token_data.get('bundlersHolding', 0)),
                'top10Holding': float(token_data.get('top10Holding', 0)),
                'buysCount': int(token_data.get('buysCount', 0)),
                'sellsCount': int(token_data.get('sellsCount', 0)),
                'twitter': token_data.get('twitter', ''),
                'website': token_data.get('website', ''),
                'telegram': token_data.get('telegram', ''),
                'discord': token_data.get('discord', ''),
                'source': 'phantom',
                'rawData': token_data  # Keep raw data for debugging
            }
            
            return standardized
            
        except Exception as e:
            logger.error(f"Error standardizing token data: {e}")
            logger.debug(f"Token data that caused error: {token_data}")
            return None
    
    def scan_new_launches(self) -> List[Dict[str, Any]]:
        """
        Scan for new token launches on Phantom.com.
        
        Returns:
            List of newly launched tokens in standardized format
        """
        logger.info("Scanning Phantom.com for new token launches")
        
        # Fetch the raw HTML
        html_content = self.fetch_launch_data()
        if not html_content:
            logger.warning("Failed to fetch Phantom.com launch data")
            return []
        
        # Parse and standardize the data
        tokens = self.parse_launch_data(html_content)
        logger.info(f"Found {len(tokens)} new tokens from Phantom.com")
        
        return tokens

# Convenience function for easy scanning
def scan_phantom_launches() -> List[Dict[str, Any]]:
    """
    Convenience function to scan Phantom.com for new token launches.
    
    Returns:
        List of token dictionaries in standardized format
    """
    scanner = PhantomLauncherScanner()
    return scanner.scan_new_launches()

# For testing purposes
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    scanner = PhantomLauncherScanner()
    tokens = scanner.scan_new_launches()
    
    print(f"Found {len(tokens)} tokens:")
    for token in tokens[:3]:  # Show first 3
        print(f"- {token.get('symbol')} ({token.get('name')}): ${token.get('marketCap', 0):.2f} MC")