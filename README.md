# AI Research Assistant

## Overview
A microservice driven implementation for transforming PDFs into engaging audio content. For a deeper dive into the system architecture, please see the diagram below:

You can view a mermaid diagram of our system [here](docs/README.md).

## Quick Start Guide

1. **Environment Variables**:
   We require the following environment variables to be set:
   ```bash
   # Create .env file with required variables
   echo "ELEVENLABS_API_KEY=your_key" > .env
   echo "NIM_KEY=your_key" >> .env
   echo "MAX_CONCURRENT_REQUESTS=1" >> .env
   ```

   Note that in production we use the NVIDIA Eleven Labs API key which can handle concurrent requests. For local development, you may want to set `MAX_CONCURRENT_REQUESTS=1` to avoid rate limiting issues. You can generate your own testing API key for free [here](https://elevenlabs.io/).

2. **Install Dependencies**:
   We use UV to manage python dependencies.
   
   ```bash
   make uv
   ```
   This will:
   - Install UV if not present
   - Create virtual environment
   - Install project dependencies

   If you open up a new terminal window and want to quickly re-use the same environment, you can run `make uv` again.

3. **Start Development Server**:
   You can start the entire stack with:
   ```bash
   make all-services
   ```

   This command will:
   - Verify environment variables are set
   - Create necessary directories
   - Start all services using Docker Compose in `--build` mode. 

   > **Note:** The first time you run `make all-services`, the `docling` service may take 10-15 minutes to pull and build. Subsequent runs will be much faster.

   You can also set `DETACH=1` to run the services in detached mode, which allows you to continue using your terminal while the services are running.

4. **Run Podcast Generation**:
   ```bash
   python tests/test.py --target <pdf1.pdf> --context <pdf2.pdf>
   ```

   This will generate a 2-person podcast. In order to generate a 1-person monologue, you can add the `--monologue` flag. Check out the test file for more examples. If you are not on a GPU machine, the PDF service might take a while to run.

## Hosting the PDF service on a separate machine

As stated above, we use [docling](https://github.com/DS4SD/docling) as our default PDF service. When you spin up the stack, docling will be built and run automatically.

If you would like to run the PDF service on a separate machine, you can add the following to your `.env` file:
```bash
echo "MODEL_API_URL=<pdf-model-service-url" >> .env
```

### Using `nv-ingest`

We also support using a fork of NVIDIA's [NV-Ingest](https://github.com/NVIDIA/NV-Ingest) as our PDF service. This requires 2 A100-SXM machines. See the [repo](https://github.com/jdye64/nv-ingest/tree/brev-dev-convert-endpoint) for more information. If you would like to use this, you can add the following to your `.env` file:
```bash
echo "MODEL_API_URL=<nv-ingest-url>/v1" >> .env
```
**Note the use of `v1` in the URL.**    

Here is the workflow that we use for running this in production (disaggregated core services and pdf model service):
```bash
# On an L40s machine
make model-prod

# On a different machine
make prod
```

## Development Tools

### Tracing
We expose a Jaeger instance at `http://localhost:16686/` for tracing. This is useful for debugging and monitoring the system.

### Code Quality
The project uses `ruff` for linting and formatting. You must run `make ruff` before your PR can be merged:
```bash
make ruff  # Runs both lint and format
```

## CI/CD
We use GitHub Actions for CI/CD. We run the following actions:
- `ruff`: Runs linting and formatting
- `pr-test`: Runs an e2e podcast test on the PR
- `build-and-push`: Builds and pushes a new container image to the remote repo. This is used to update production deployments

## Production Deployment
For production deployment:
```bash
make prod
```

This uses the remote Docker Compose configuration and pulls pre-built images from the registry.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python tests/test.py <pdf1> <pdf2>`
5. Run linting: `make ruff`
6. Submit a pull request