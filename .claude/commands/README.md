# Claude Commands

Custom commands for the Revolut Trader project. These are specialized workflows that Claude can execute.

## Available Commands

### 1. `audit-docs`

**Purpose**: Comprehensive documentation review and improvement

Reviews and fixes:

- Project structure accuracy in README
- Command documentation vs actual Makefile
- Architecture documentation accuracy
- Links and references validity
- Workflow configurations
- Documentation consistency

**When to use**: After major changes to codebase structure, before releases, or when documentation feels stale.

**Usage**:

```
/audit-docs
```

### 2. `code-improvement`

**Purpose**: Comprehensive code quality and modernization review

Analyzes and suggests improvements for:

- Dependency updates (check for newer package versions)
- Python version features and modern syntax
- Code quality patterns and best practices
- Test coverage gaps and quality
- CI/CD workflow optimizations
- Performance opportunities
- Security vulnerabilities and best practices
- Developer tooling and experience
- Architecture and design patterns
- Technical debt prioritization

**Output**: Structured report with:

- Executive summary with quality score
- Top 5 most impactful recommendations
- Quick wins (low-effort, high-impact)
- Long-term strategic improvements
- Dependency update table
- Prioritized backlog (Critical/High/Medium/Low)

**When to use**:

- Monthly or quarterly maintenance reviews
- After major feature additions
- Before production releases
- When planning technical debt work
- When evaluating new tools/packages

**Usage**:

```
/code-improvement
```

### 3. `revolut-api`

**Purpose**: Quick reference for Revolut X API endpoints

Provides structured documentation for all 17 API endpoints:

- Authentication
- Trading (orders, market orders, cancel)
- Market data (tickers, order book, candles, trades)
- Account (balance, orders, historical trades)
- Error handling
- Rate limits
- Request/response models

**When to use**: When implementing or debugging API integrations.

**Usage**:

```
/revolut-api [keyword]
```

Examples:

```
/revolut-api orders      # Show order-related endpoints
/revolut-api market      # Show market data endpoints
/revolut-api errors      # Show error handling
```

## How Commands Work

Commands are markdown files that contain structured instructions for Claude. When you invoke a command:

1. Claude loads the command file
1. Executes the instructions step-by-step
1. Provides results and recommendations
1. May create/update files as needed

## Creating New Commands

To create a new command:

1. Create a markdown file in `.claude/commands/`
1. Structure it with clear sections and instructions
1. Use imperative language ("Review...", "Check...", "Suggest...")
1. Include specific file paths and criteria
1. Define expected outputs
1. Document when to use it
1. Add it to this README

### Command Template

```markdown
Brief description of what the command does and its purpose.

## 1. First Step

Clear instructions for the first step:
- Bullet point
- Another action
- Specific file to check

## 2. Second Step

Next set of instructions...

## N. Summary

Provide a summary of findings/changes.
```

## Best Practices

1. **Run commands periodically**: Regular maintenance prevents issues
1. **Review outputs carefully**: Commands provide suggestions, you make decisions
1. **Combine commands**: e.g., `code-improvement` then `audit-docs`
1. **Document decisions**: Note why you accept/reject suggestions
1. **Test after changes**: Always run tests after applying suggestions

## Command Execution Tips

- Commands can take several minutes for comprehensive reviews
- Let them complete fully before making changes
- Commands may create temporary files or notes
- Review all changes before committing
- Commands respect the project's coding standards

## Troubleshooting

**Command not found**: Ensure the `.md` file exists in `.claude/commands/`

**Command doesn't execute**: Check the markdown formatting and structure

**Unexpected results**: Review the command file and update instructions

**Want to modify a command**: Edit the `.md` file directly

## Future Commands (Ideas)

Potential commands to add:

- `security-audit` - Deep security review
- `performance-profile` - Identify performance bottlenecks
- `test-quality` - Review test effectiveness
- `dependency-audit` - Deep dive on dependencies
- `release-checklist` - Pre-release validation
- `database-review` - Database schema and query optimization
- `api-coverage` - Ensure all API endpoints are tested
- `error-handling-audit` - Review error handling patterns
