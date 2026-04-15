#!/usr/bin/env python3
"""
Principle Review Script - CLI interface for managing the review queue.

Week 4 Implementation - CSP Workflow Engine Self-Learning Module

Usage:
    python script.py list                    # List pending principles
    python script.py stats                   # Show queue statistics
    python script.py approve <id>            # Approve a principle
    python script.py reject <id>             # Reject a principle
    python script.py edit <id>               # Edit a principle
    python script.py show <id>               # Show principle details
"""

import sys
import argparse
import json
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from principle_validator import PrincipleValidator, QueuedPrinciple


def format_principle_summary(p: QueuedPrinciple, index: int = None) -> str:
    """Format a principle for display."""
    prefix = f"{index}. " if index is not None else ""
    type_emoji = "[GUIDING]" if p.type == "guiding" else "[CAUTION]"

    lines = [
        f"{prefix}{type_emoji} {p.principle_id}",
        f"   Description: {p.description[:77]}..." if len(p.description) > 80 else f"   Description: {p.description}",
        f"   Nodes: {', '.join(p.applicable_nodes[:3])}" + ("..." if len(p.applicable_nodes) > 3 else ""),
        f"   Queued: {p.queued_at}",
    ]

    if p.failure_reasons:
        lines.append(f"   Failures: {', '.join(p.failure_reasons[:2])}")

    return '\n'.join(lines)


def format_principle_detail(p: QueuedPrinciple) -> str:
    """Format a principle with full details."""
    lines = [
        f"Principle ID: {p.principle_id}",
        f"Type: {p.type}",
        f"Status: {p.review_status}",
        "",
        "Description:",
        f"  {p.description}",
        "",
        f"Applicable Nodes: {', '.join(p.applicable_nodes) if p.applicable_nodes else 'None'}",
        f"Applicable Layers: {', '.join(map(str, p.applicable_layers)) if p.applicable_layers else 'None'}",
        "",
        f"Skills Recommended: {', '.join(p.skills_recommended) if p.skills_recommended else 'None'}",
        f"Validation Checks: {', '.join(p.validation_checks) if p.validation_checks else 'None'}",
        "",
        f"Source Trajectories: {', '.join(p.source_trajectory_ids) if p.source_trajectory_ids else 'None'}",
        f"Created: {p.created_at}",
        f"Queued: {p.queued_at}",
    ]

    if p.failure_reasons:
        lines.extend([
            "",
            "Quality Gate Failures:",
        ])
        for reason in p.failure_reasons:
            lines.append(f"  - {reason}")

    if p.reviewer:
        lines.extend([
            "",
            f"Reviewer: {p.reviewer}",
            f"Reviewed At: {p.reviewed_at}",
        ])

    return '\n'.join(lines)


def cmd_list(args):
    """List all pending principles in the review queue."""
    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    queued = validator.get_review_queue()

    if not queued:
        print("No pending principles in review queue.")
        return 0

    print(f"Review Queue ({len(queued)} pending):\n")
    for i, p in enumerate(queued, 1):
        print(format_principle_summary(p, i))
        print()

    return 0


def cmd_stats(args):
    """Show queue statistics."""
    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    pending = validator.count_queue('pending')
    approved = validator.count_queue('approved')
    rejected = validator.count_queue('rejected')

    print("Review Queue Statistics")
    print("=" * 40)
    print(f"  Pending:   {pending}")
    print(f"  Approved:  {approved}")
    print(f"  Rejected:  {rejected}")
    print(f"  Total:     {pending + approved + rejected}")
    print()

    # Show recent activity
    if approved > 0:
        print(f"Recent approvals stored in: {args.queue_path}/approved/")

    return 0


def cmd_show(args):
    """Show details of a specific principle."""
    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    queued = validator.get_review_queue()
    principle = next((p for p in queued if p.principle_id == args.principle_id), None)

    if not principle:
        print(f"Principle {args.principle_id} not found in queue.")
        return 1

    print(format_principle_detail(principle))
    return 0


def cmd_approve(args):
    """Approve a principle and add it to the store."""
    from principle_store import PrincipleStore, RegulatoryPrinciple

    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    # Approve in queue
    if not validator.approve_principle(args.principle_id, args.reviewer):
        print(f"Principle {args.principle_id} not found in queue.")
        return 1

    # Get approved principle
    approved = validator.get_approved_principle(args.principle_id)
    if not approved:
        print(f"Error: Could not retrieve approved principle.")
        return 1

    # Add to principle store
    store = PrincipleStore(args.store_path)
    principle = RegulatoryPrinciple(
        principle_id=approved.principle_id,
        type=approved.type,
        description=approved.description,
        applicable_nodes=approved.applicable_nodes,
        applicable_layers=approved.applicable_layers,
        skills_recommended=approved.skills_recommended,
        validation_checks=approved.validation_checks,
        source_trajectory_ids=approved.source_trajectory_ids,
        created_at=approved.created_at
    )

    if store.add_principle(principle):
        print(f"Principle {args.principle_id} approved and added to store.")
        print(f"  Reviewer: {args.reviewer}")
        print(f"  Approved at: {datetime.now().isoformat()}")
        return 0
    else:
        print(f"Warning: Principle {args.principle_id} was approved but not added to store (duplicate?).")
        return 1


def cmd_reject(args):
    """Reject a principle."""
    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    if not validator.reject_principle(args.principle_id, args.reviewer, args.reason):
        print(f"Principle {args.principle_id} not found in queue.")
        return 1

    print(f"Principle {args.principle_id} rejected.")
    print(f"  Reviewer: {args.reviewer}")
    if args.reason:
        print(f"  Reason: {args.reason}")
    return 0


def cmd_edit(args):
    """Edit a principle then approve it."""
    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )

    # Get the principle
    queued = validator.get_review_queue()
    principle = next((p for p in queued if p.principle_id == args.principle_id), None)

    if not principle:
        print(f"Principle {args.principle_id} not found in queue.")
        return 1

    # Create temp file for editing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({
            'principle_id': principle.principle_id,
            'type': principle.type,
            'description': principle.description,
            'applicable_nodes': principle.applicable_nodes,
            'applicable_layers': principle.applicable_layers,
            'skills_recommended': principle.skills_recommended,
            'validation_checks': principle.validation_checks,
        }, f, indent=2)
        temp_path = f.name

    # Open editor
    editor = args.editor or 'notepad' if sys.platform == 'win32' else 'nano'
    try:
        subprocess.run([editor, temp_path], check=True)
    except subprocess.CalledProcessError:
        print(f"Editor exited with error. Aborting.")
        Path(temp_path).unlink()
        return 1
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Please specify --editor.")
        Path(temp_path).unlink()
        return 1

    # Read edited content
    with open(temp_path, 'r') as f:
        edited = json.load(f)

    Path(temp_path).unlink()

    # Update principle
    principle.description = edited.get('description', principle.description)
    principle.applicable_nodes = edited.get('applicable_nodes', principle.applicable_nodes)
    principle.applicable_layers = edited.get('applicable_layers', principle.applicable_layers)
    principle.skills_recommended = edited.get('skills_recommended', principle.skills_recommended)
    principle.validation_checks = edited.get('validation_checks', principle.validation_checks)

    # Save edited version to queue (overwrite)
    queue_path = Path(args.queue_path) / f"{principle.principle_id}.json"
    with open(queue_path, 'w') as f:
        json.dump({
            'principle_id': principle.principle_id,
            'type': principle.type,
            'description': principle.description,
            'applicable_nodes': principle.applicable_nodes,
            'applicable_layers': principle.applicable_layers,
            'skills_recommended': principle.skills_recommended,
            'validation_checks': principle.validation_checks,
            'source_trajectory_ids': principle.source_trajectory_ids,
            'created_at': principle.created_at,
            'queued_at': principle.queued_at,
            'failure_reasons': principle.failure_reasons,
            'review_status': 'edited',
            'reviewer': args.reviewer,
            'reviewed_at': datetime.now().isoformat(),
        }, f, indent=2)

    print(f"Principle {args.principle_id} edited.")
    print("Run 'approve' command to add it to the store.")

    return 0


def cmd_batch_approve(args):
    """Approve all principles that pass validation."""
    from principle_store import PrincipleStore, RegulatoryPrinciple

    validator = PrincipleValidator(
        review_queue_path=args.queue_path,
        auto_approve=False
    )
    store = PrincipleStore(args.store_path)

    queued = validator.get_review_queue()
    approved_count = 0
    rejected_count = 0

    for p in queued:
        # Create a temporary principle for validation
        from principle_store import RegulatoryPrinciple
        temp_principle = RegulatoryPrinciple(
            principle_id=p.principle_id,
            type=p.type,
            description=p.description,
            applicable_nodes=p.applicable_nodes,
            applicable_layers=p.applicable_layers,
            skills_recommended=p.skills_recommended,
            validation_checks=p.validation_checks,
            metric_score=0.5,  # Default for re-validation
            usage_count=3  # Default for re-validation
        )

        result = validator.validate(temp_principle)

        if result.passed:
            validator.approve_principle(p.principle_id, args.reviewer)
            principle = RegulatoryPrinciple(
                principle_id=p.principle_id,
                type=p.type,
                description=p.description,
                applicable_nodes=p.applicable_nodes,
                applicable_layers=p.applicable_layers,
                skills_recommended=p.skills_recommended,
                validation_checks=p.validation_checks,
                source_trajectory_ids=p.source_trajectory_ids,
                created_at=p.created_at
            )
            if store.add_principle(principle):
                approved_count += 1
                print(f"  Approved: {p.principle_id}")
        else:
            print(f"  Skipped: {p.principle_id} ({result.failures[0]})")
            rejected_count += 1

    print(f"\nBatch complete: {approved_count} approved, {rejected_count} skipped.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Principle Review - Manage the review queue for self-learning principles'
    )
    parser.add_argument(
        '--queue-path',
        default='data/experiences/review_queue',
        help='Path to review queue directory'
    )
    parser.add_argument(
        '--store-path',
        default='data/experiences/principles.db',
        help='Path to principle store database'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # list command
    subparsers.add_parser('list', help='List pending principles')

    # stats command
    subparsers.add_parser('stats', help='Show queue statistics')

    # show command
    show_parser = subparsers.add_parser('show', help='Show principle details')
    show_parser.add_argument('principle_id', help='Principle ID to show')

    # approve command
    approve_parser = subparsers.add_parser('approve', help='Approve a principle')
    approve_parser.add_argument('principle_id', help='Principle ID to approve')
    approve_parser.add_argument('--reviewer', '-r', default='admin', help='Reviewer ID')

    # reject command
    reject_parser = subparsers.add_parser('reject', help='Reject a principle')
    reject_parser.add_argument('principle_id', help='Principle ID to reject')
    reject_parser.add_argument('--reviewer', '-r', default='admin', help='Reviewer ID')
    reject_parser.add_argument('--reason', help='Rejection reason')

    # edit command
    edit_parser = subparsers.add_parser('edit', help='Edit a principle')
    edit_parser.add_argument('principle_id', help='Principle ID to edit')
    edit_parser.add_argument('--reviewer', '-r', default='admin', help='Reviewer ID')
    edit_parser.add_argument('--editor', help='Editor to use (default: notepad on Windows, nano otherwise)')

    # batch-approve command
    batch_parser = subparsers.add_parser('batch-approve', help='Approve all valid principles')
    batch_parser.add_argument('--reviewer', '-r', default='admin', help='Reviewer ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        'list': cmd_list,
        'stats': cmd_stats,
        'show': cmd_show,
        'approve': cmd_approve,
        'reject': cmd_reject,
        'edit': cmd_edit,
        'batch-approve': cmd_batch_approve,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
