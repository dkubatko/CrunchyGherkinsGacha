#!/usr/bin/env python3
"""Profile the single aspect/card image endpoint to find bottlenecks.

Measures wall-clock time of each stage:
  1. DB session acquisition
  2. Season-validation query (OwnedAspectModel / CardModel)
  3. Image query (AspectImageModel / CardImageModel)
  4. base64 encoding
  5. JSON serialization (FastAPI response_model=str wraps in JSON quotes)

Also profiles the card image path for comparison.

Usage:
    cd bot/
    python -m tools.profile_image_endpoint
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import statistics

# Ensure we can import the bot package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost:5432/gacha")


def setup():
    """Minimal bootstrap — engine + session only."""
    from utils.session import initialize_session
    initialize_session(pool_size=4, timeout_seconds=10)


def profile_aspect_image(aspect_id: int, iterations: int = 20):
    """Profile get_aspect_image step-by-step."""
    from utils.session import get_session
    from utils.models import OwnedAspectModel, AspectImageModel
    from settings.constants import CURRENT_SEASON

    print(f"\n{'='*70}")
    print(f"  Profiling ASPECT image (id={aspect_id}, {iterations} iterations)")
    print(f"{'='*70}")

    timings = {
        "session_acquire": [],
        "season_query": [],
        "image_query": [],
        "b64_encode": [],
        "json_serialize": [],
        "total": [],
    }

    image_size_bytes = 0

    for i in range(iterations):
        t_total_start = time.perf_counter()

        # 1. Session acquisition
        t0 = time.perf_counter()
        session = None
        try:
            ctx = get_session()
            session = ctx.__enter__()
            t1 = time.perf_counter()
            timings["session_acquire"].append(t1 - t0)

            # 2. Season-validation query
            t0 = time.perf_counter()
            aspect = (
                session.query(OwnedAspectModel)
                .filter(
                    OwnedAspectModel.id == aspect_id,
                    OwnedAspectModel.season_id == CURRENT_SEASON,
                )
                .first()
            )
            t1 = time.perf_counter()
            timings["season_query"].append(t1 - t0)

            if not aspect:
                print(f"  ⚠ Aspect {aspect_id} not found in season {CURRENT_SEASON}")
                return

            # 3. Image query
            t0 = time.perf_counter()
            aspect_image = (
                session.query(AspectImageModel)
                .filter(AspectImageModel.aspect_id == aspect_id)
                .first()
            )
            t1 = time.perf_counter()
            timings["image_query"].append(t1 - t0)

            if not aspect_image or not aspect_image.image:
                print(f"  ⚠ No image data for aspect {aspect_id}")
                return

            raw_bytes = aspect_image.image
            if i == 0:
                image_size_bytes = len(raw_bytes)

            # 4. base64 encode
            t0 = time.perf_counter()
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            t1 = time.perf_counter()
            timings["b64_encode"].append(t1 - t0)

            # 5. JSON serialization (FastAPI wraps str in JSON quotes)
            t0 = time.perf_counter()
            _ = json.dumps(b64)
            t1 = time.perf_counter()
            timings["json_serialize"].append(t1 - t0)

        finally:
            if session:
                ctx.__exit__(None, None, None)

        t_total_end = time.perf_counter()
        timings["total"].append(t_total_end - t_total_start)

    # Report
    b64_size = len(base64.b64encode(b"\x00" * image_size_bytes))
    print(f"\n  Image size: {image_size_bytes:,} bytes raw → {b64_size:,} bytes base64")
    print(f"  JSON payload: ~{b64_size + 2:,} bytes\n")

    print(f"  {'Stage':<20} {'Mean':>10} {'Median':>10} {'p95':>10} {'Min':>10} {'Max':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for stage, values in timings.items():
        if not values:
            continue
        sorted_v = sorted(values)
        mean = statistics.mean(sorted_v) * 1000
        med = statistics.median(sorted_v) * 1000
        p95 = sorted_v[int(len(sorted_v) * 0.95)] * 1000
        mn = sorted_v[0] * 1000
        mx = sorted_v[-1] * 1000
        print(f"  {stage:<20} {mean:>8.2f}ms {med:>8.2f}ms {p95:>8.2f}ms {mn:>8.2f}ms {mx:>8.2f}ms")


def profile_card_image(card_id: int, iterations: int = 20):
    """Profile get_card_image step-by-step."""
    from utils.session import get_session
    from utils.models import CardModel, CardImageModel
    from settings.constants import CURRENT_SEASON

    print(f"\n{'='*70}")
    print(f"  Profiling CARD image (id={card_id}, {iterations} iterations)")
    print(f"{'='*70}")

    timings = {
        "session_acquire": [],
        "season_query": [],
        "image_query": [],
        "b64_encode": [],
        "json_serialize": [],
        "total": [],
    }

    image_size_bytes = 0

    for i in range(iterations):
        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        session = None
        try:
            ctx = get_session()
            session = ctx.__enter__()
            t1 = time.perf_counter()
            timings["session_acquire"].append(t1 - t0)

            t0 = time.perf_counter()
            card = (
                session.query(CardModel)
                .filter(
                    CardModel.id == card_id,
                    CardModel.season_id == CURRENT_SEASON,
                )
                .first()
            )
            t1 = time.perf_counter()
            timings["season_query"].append(t1 - t0)

            if not card:
                print(f"  ⚠ Card {card_id} not found in season {CURRENT_SEASON}")
                return

            t0 = time.perf_counter()
            card_image = (
                session.query(CardImageModel)
                .filter(CardImageModel.card_id == card_id)
                .first()
            )
            t1 = time.perf_counter()
            timings["image_query"].append(t1 - t0)

            if not card_image or not card_image.image:
                print(f"  ⚠ No image data for card {card_id}")
                return

            raw_bytes = card_image.image
            if i == 0:
                image_size_bytes = len(raw_bytes)

            t0 = time.perf_counter()
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            t1 = time.perf_counter()
            timings["b64_encode"].append(t1 - t0)

            t0 = time.perf_counter()
            _ = json.dumps(b64)
            t1 = time.perf_counter()
            timings["json_serialize"].append(t1 - t0)

        finally:
            if session:
                ctx.__exit__(None, None, None)

        t_total_end = time.perf_counter()
        timings["total"].append(t_total_end - t_total_start)

    b64_size = len(base64.b64encode(b"\x00" * image_size_bytes))
    print(f"\n  Image size: {image_size_bytes:,} bytes raw → {b64_size:,} bytes base64")
    print(f"  JSON payload: ~{b64_size + 2:,} bytes\n")

    print(f"  {'Stage':<20} {'Mean':>10} {'Median':>10} {'p95':>10} {'Min':>10} {'Max':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for stage, values in timings.items():
        if not values:
            continue
        sorted_v = sorted(values)
        mean = statistics.mean(sorted_v) * 1000
        med = statistics.median(sorted_v) * 1000
        p95 = sorted_v[int(len(sorted_v) * 0.95)] * 1000
        mn = sorted_v[0] * 1000
        mx = sorted_v[-1] * 1000
        print(f"  {stage:<20} {mean:>8.2f}ms {med:>8.2f}ms {p95:>8.2f}ms {mn:>8.2f}ms {mx:>8.2f}ms")


def profile_thumbnail(aspect_id: int, iterations: int = 20):
    """Profile thumbnail path (with potential on-the-fly generation)."""
    from utils.session import get_session
    from utils.models import OwnedAspectModel, AspectImageModel
    from utils.image import ImageUtil
    from settings.constants import CURRENT_SEASON

    print(f"\n{'='*70}")
    print(f"  Profiling ASPECT THUMBNAIL (id={aspect_id}, {iterations} iterations)")
    print(f"{'='*70}")

    timings = {
        "session_acquire": [],
        "season_query": [],
        "image_query": [],
        "thumb_generate": [],
        "b64_encode": [],
        "total": [],
    }

    for i in range(iterations):
        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        session = None
        try:
            ctx = get_session()
            session = ctx.__enter__()
            t1 = time.perf_counter()
            timings["session_acquire"].append(t1 - t0)

            t0 = time.perf_counter()
            aspect = (
                session.query(OwnedAspectModel)
                .filter(
                    OwnedAspectModel.id == aspect_id,
                    OwnedAspectModel.season_id == CURRENT_SEASON,
                )
                .first()
            )
            t1 = time.perf_counter()
            timings["season_query"].append(t1 - t0)

            if not aspect:
                print(f"  ⚠ Aspect {aspect_id} not found")
                return

            t0 = time.perf_counter()
            aspect_image = (
                session.query(AspectImageModel)
                .filter(AspectImageModel.aspect_id == aspect_id)
                .first()
            )
            t1 = time.perf_counter()
            timings["image_query"].append(t1 - t0)

            if not aspect_image:
                print(f"  ⚠ No image record for aspect {aspect_id}")
                return

            # Thumbnail generation (simulated — don't persist to avoid polluting data)
            if aspect_image.image:
                t0 = time.perf_counter()
                thumb_bytes = ImageUtil.compress_to_fraction(aspect_image.image, scale_factor=1 / 4)
                t1 = time.perf_counter()
                timings["thumb_generate"].append(t1 - t0)

                t0 = time.perf_counter()
                _ = base64.b64encode(thumb_bytes).decode("utf-8")
                t1 = time.perf_counter()
                timings["b64_encode"].append(t1 - t0)
            else:
                print(f"  ⚠ No image data for aspect {aspect_id}")
                return

        finally:
            if session:
                ctx.__exit__(None, None, None)

        t_total_end = time.perf_counter()
        timings["total"].append(t_total_end - t_total_start)

    print()
    print(f"  {'Stage':<20} {'Mean':>10} {'Median':>10} {'p95':>10} {'Min':>10} {'Max':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for stage, values in timings.items():
        if not values:
            continue
        sorted_v = sorted(values)
        mean = statistics.mean(sorted_v) * 1000
        med = statistics.median(sorted_v) * 1000
        p95 = sorted_v[int(len(sorted_v) * 0.95)] * 1000
        mn = sorted_v[0] * 1000
        mx = sorted_v[-1] * 1000
        print(f"  {stage:<20} {mean:>8.2f}ms {med:>8.2f}ms {p95:>8.2f}ms {mn:>8.2f}ms {mx:>8.2f}ms")


def find_sample_ids():
    """Find a valid aspect and card ID for profiling."""
    from utils.session import get_session
    from utils.models import AspectImageModel, CardImageModel, OwnedAspectModel, CardModel
    from settings.constants import CURRENT_SEASON

    with get_session() as session:
        aspect_row = (
            session.query(OwnedAspectModel.id)
            .join(AspectImageModel, AspectImageModel.aspect_id == OwnedAspectModel.id)
            .filter(
                OwnedAspectModel.season_id == CURRENT_SEASON,
                AspectImageModel.image.isnot(None),
            )
            .first()
        )
        card_row = (
            session.query(CardModel.id)
            .join(CardImageModel, CardImageModel.card_id == CardModel.id)
            .filter(
                CardModel.season_id == CURRENT_SEASON,
                CardImageModel.image.isnot(None),
            )
            .first()
        )

    aspect_id = aspect_row[0] if aspect_row else None
    card_id = card_row[0] if card_row else None
    return aspect_id, card_id


def main():
    setup()

    aspect_id, card_id = find_sample_ids()
    print(f"\nSample IDs — aspect: {aspect_id}, card: {card_id}")

    if aspect_id:
        profile_aspect_image(aspect_id)
        profile_thumbnail(aspect_id)
    else:
        print("  No aspect with image found — skipping aspect profiles")

    if card_id:
        profile_card_image(card_id)
    else:
        print("  No card with image found — skipping card profile")


if __name__ == "__main__":
    main()
