"""
Domain List Management for Security

Manages whitelist and blacklist of domains for information gathering.
Provides automatic blacklisting of malicious sources.
"""

import json
import os
import logging
from datetime import datetime
from typing import Set, Dict, Optional, List
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainListManager:
    """
    Manages whitelist and blacklist for information gathering security

    Features:
    - Whitelist: Trusted domains (fast regex check only)
    - Blacklist: Malicious domains (block immediately)
    - Auto-blacklisting on threat detection
    - Persistent storage
    - Human review queue
    """

    def __init__(self, data_dir: str = "./data/security"):
        """
        Initialize domain list manager

        Args:
            data_dir: Directory for storing lists
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.whitelist_file = self.data_dir / "whitelist.json"
        self.blacklist_file = self.data_dir / "blacklist.json"
        self.review_queue_file = self.data_dir / "review_queue.json"

        # Load lists
        self.whitelist: Set[str] = self._load_whitelist()
        self.blacklist: Dict[str, Dict] = self._load_blacklist()
        self.review_queue: List[Dict] = self._load_review_queue()

        logger.info(
            f"Domain lists loaded: "
            f"whitelist={len(self.whitelist)}, "
            f"blacklist={len(self.blacklist)}, "
            f"review_queue={len(self.review_queue)}"
        )

    def _load_whitelist(self) -> Set[str]:
        """Load whitelist from file"""
        if not self.whitelist_file.exists():
            # Default trusted financial news sources
            default_whitelist = {
                "finance.yahoo.com",
                "bloomberg.com",
                "reuters.com",
                "sec.gov",
                "investor.gov",
                "marketwatch.com",
                "cnbc.com",
                "wsj.com",
                "ft.com",
                "barrons.com",
                "nasdaq.com",
                "nyse.com",
            }
            self._save_whitelist(default_whitelist)
            return default_whitelist

        try:
            with open(self.whitelist_file, 'r') as f:
                data = json.load(f)
                return set(data.get("domains", []))
        except Exception as e:
            logger.error(f"Error loading whitelist: {e}")
            return set()

    def _load_blacklist(self) -> Dict[str, Dict]:
        """Load blacklist from file"""
        if not self.blacklist_file.exists():
            return {}

        try:
            with open(self.blacklist_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading blacklist: {e}")
            return {}

    def _load_review_queue(self) -> List[Dict]:
        """Load review queue from file"""
        if not self.review_queue_file.exists():
            return []

        try:
            with open(self.review_queue_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading review queue: {e}")
            return []

    def _save_whitelist(self, whitelist: Set[str]):
        """Save whitelist to file"""
        try:
            with open(self.whitelist_file, 'w') as f:
                json.dump({
                    "domains": sorted(list(whitelist)),
                    "updated_at": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving whitelist: {e}")

    def _save_blacklist(self):
        """Save blacklist to file"""
        try:
            with open(self.blacklist_file, 'w') as f:
                json.dump(self.blacklist, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving blacklist: {e}")

    def _save_review_queue(self):
        """Save review queue to file"""
        try:
            with open(self.review_queue_file, 'w') as f:
                json.dump(self.review_queue, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving review queue: {e}")

    def extract_domain(self, url: str) -> str:
        """
        Extract domain from URL

        Args:
            url: Full URL

        Returns:
            Domain name (e.g., "example.com")
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            return domain
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return ""

    def is_whitelisted(self, url: str) -> bool:
        """
        Check if URL is whitelisted

        Args:
            url: URL to check

        Returns:
            True if whitelisted, False otherwise
        """
        domain = self.extract_domain(url)
        return domain in self.whitelist

    def is_blacklisted(self, url: str) -> bool:
        """
        Check if URL is blacklisted

        Args:
            url: URL to check

        Returns:
            True if blacklisted, False otherwise
        """
        domain = self.extract_domain(url)
        return domain in self.blacklist

    def get_blacklist_reason(self, url: str) -> Optional[str]:
        """
        Get reason for blacklisting

        Args:
            url: URL to check

        Returns:
            Reason string or None
        """
        domain = self.extract_domain(url)
        if domain in self.blacklist:
            return self.blacklist[domain].get("reason", "Unknown")
        return None

    def add_to_blacklist(
        self,
        url: str,
        reason: str,
        threats: List[str],
        risk_score: float,
        auto_added: bool = True
    ):
        """
        Add domain to blacklist

        Args:
            url: URL that was malicious
            reason: Reason for blacklisting
            threats: List of detected threats
            risk_score: Risk score (0.0 - 1.0)
            auto_added: If True, was automatically added
        """
        domain = self.extract_domain(url)

        if not domain:
            logger.warning(f"Could not extract domain from {url}")
            return

        # Add to blacklist
        self.blacklist[domain] = {
            "reason": reason,
            "threats": threats,
            "risk_score": risk_score,
            "example_url": url,
            "added_at": datetime.now().isoformat(),
            "auto_added": auto_added,
            "review_status": "pending" if auto_added else "confirmed"
        }

        self._save_blacklist()

        # Add to review queue if auto-added
        if auto_added:
            self.add_to_review_queue(url, reason, threats, risk_score)

        logger.warning(
            f"🚨 BLACKLISTED: {domain}\n"
            f"   Reason: {reason}\n"
            f"   Risk: {risk_score:.2f}\n"
            f"   Threats: {threats}\n"
            f"   Review: {'REQUIRED' if auto_added else 'Confirmed'}"
        )

    def add_to_review_queue(
        self,
        url: str,
        reason: str,
        threats: List[str],
        risk_score: float
    ):
        """
        Add entry to human review queue

        Args:
            url: URL that triggered the alert
            reason: Detection reason
            threats: List of threats
            risk_score: Risk score
        """
        domain = self.extract_domain(url)

        # Check if already in queue
        for item in self.review_queue:
            if item.get("domain") == domain:
                # Update existing entry
                item["occurrences"] = item.get("occurrences", 1) + 1
                item["last_seen"] = datetime.now().isoformat()
                self._save_review_queue()
                return

        # Add new entry
        self.review_queue.append({
            "domain": domain,
            "url": url,
            "reason": reason,
            "threats": threats,
            "risk_score": risk_score,
            "added_at": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "occurrences": 1,
            "reviewed": False
        })

        self._save_review_queue()

        logger.info(
            f"📋 Added to review queue: {domain}\n"
            f"   Queue size: {len(self.review_queue)}"
        )

    def add_to_whitelist(self, url: str):
        """
        Add domain to whitelist

        Args:
            url: URL to whitelist
        """
        domain = self.extract_domain(url)

        if not domain:
            logger.warning(f"Could not extract domain from {url}")
            return

        self.whitelist.add(domain)
        self._save_whitelist(self.whitelist)

        # Remove from blacklist if present
        if domain in self.blacklist:
            del self.blacklist[domain]
            self._save_blacklist()

        logger.info(f"✅ WHITELISTED: {domain}")

    def remove_from_blacklist(self, domain: str):
        """
        Remove domain from blacklist (after human review)

        Args:
            domain: Domain to remove
        """
        if domain in self.blacklist:
            del self.blacklist[domain]
            self._save_blacklist()
            logger.info(f"Removed from blacklist: {domain}")

    def mark_reviewed(self, domain: str, action: str = "keep"):
        """
        Mark domain as reviewed in queue

        Args:
            domain: Domain that was reviewed
            action: Action taken (keep, remove, whitelist)
        """
        for item in self.review_queue:
            if item.get("domain") == domain:
                item["reviewed"] = True
                item["review_action"] = action
                item["reviewed_at"] = datetime.now().isoformat()

        self._save_review_queue()

        if action == "remove":
            self.remove_from_blacklist(domain)
        elif action == "whitelist":
            self.add_to_whitelist(f"https://{domain}")

    def get_pending_reviews(self) -> List[Dict]:
        """
        Get list of items pending human review

        Returns:
            List of pending review items
        """
        return [
            item for item in self.review_queue
            if not item.get("reviewed", False)
        ]

    def get_stats(self) -> Dict:
        """
        Get statistics about domain lists

        Returns:
            dict with stats
        """
        pending_reviews = len(self.get_pending_reviews())

        return {
            "whitelist_size": len(self.whitelist),
            "blacklist_size": len(self.blacklist),
            "pending_reviews": pending_reviews,
            "auto_blacklisted": sum(
                1 for d in self.blacklist.values()
                if d.get("auto_added", False)
            ),
            "manual_blacklisted": sum(
                1 for d in self.blacklist.values()
                if not d.get("auto_added", False)
            )
        }


# Global instance
_domain_manager: Optional[DomainListManager] = None


def get_domain_manager() -> DomainListManager:
    """Get or create global domain manager instance"""
    global _domain_manager
    if _domain_manager is None:
        _domain_manager = DomainListManager()
    return _domain_manager


if __name__ == "__main__":
    print("=" * 70)
    print("DOMAIN LIST MANAGER - TEST")
    print("=" * 70)

    manager = DomainListManager(data_dir="./test_security_data")

    print(f"\n📊 Statistics:")
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print(f"\n✅ Whitelisted domains ({len(manager.whitelist)}):")
    for domain in sorted(list(manager.whitelist))[:5]:
        print(f"   - {domain}")
    if len(manager.whitelist) > 5:
        print(f"   ... and {len(manager.whitelist) - 5} more")

    # Test checks
    print(f"\n🧪 Testing domain checks:")
    test_urls = [
        "https://finance.yahoo.com/news/test",
        "https://malicious-site.com/attack",
        "https://unknown-site.com/article"
    ]

    for url in test_urls:
        domain = manager.extract_domain(url)
        whitelisted = manager.is_whitelisted(url)
        blacklisted = manager.is_blacklisted(url)

        status = "✅ TRUSTED" if whitelisted else ("🚫 BLOCKED" if blacklisted else "⚠️  UNKNOWN")
        print(f"   {status}: {domain}")

    # Test blacklisting
    print(f"\n🚨 Testing blacklist addition:")
    manager.add_to_blacklist(
        "https://malicious-site.com/attack",
        reason="Prompt injection detected",
        threats=["prompt_injection", "jailbreak"],
        risk_score=0.85,
        auto_added=True
    )

    print(f"\n📋 Review queue ({len(manager.get_pending_reviews())} pending):")
    for item in manager.get_pending_reviews()[:3]:
        print(f"   - {item['domain']}: {item['reason']} (risk: {item['risk_score']:.2f})")

    print("\n" + "=" * 70)
    print("✅ DOMAIN LIST MANAGER TEST COMPLETE")
    print("=" * 70)
