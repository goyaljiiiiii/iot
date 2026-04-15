# Contributing

Thanks for your interest in improving this project.

## Development Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -e .
   ```

3. Copy environment template and update secrets locally:

   ```bash
   cp .env.example .env
   ```

## Coding Guidelines

- Keep changes focused and small.
- Preserve existing behavior unless the change explicitly targets it.
- Prefer clear names and short functions.
- Avoid committing generated files, virtual environments, or secrets.

## Pull Request Checklist

- [ ] Code runs locally.
- [ ] README or docs updated if behavior changed.
- [ ] No credentials or tokens included.
- [ ] New dependencies are justified and documented.

## Reporting Issues

When opening an issue, include:

- OS and Python version
- How to reproduce
- Relevant logs and error text
- Expected behavior vs actual behavior
