# Deployment guide

The texture creation pipeline is a Python application. However, it can be deployed in 3 different ways:
- Direct instantiation of the application
- Utilization of the provided Docker container
- Utilization of a Helm chart (for deployment in Kubernetes)

However, it is important to note that the provided application will perform a
single execution, given that it is intended to work as a periodic process,
meaning that it is instantiated periodically. As such, the provided Helm chart
is the recommended method for deployment, as it will automatically be
configured as a Kubernetes CronJob. In the case of the other deployment
methods, this behaviour must be manually configured using other tools (such as
native linux cronjobs)

## Direct instantiation

The python application was developed in a [uv](https://docs.astral.sh/uv)
managed environment. However, it is PEP-518 compliant, meaning that the `uv`
tool is not required to run the application, as the dependencies can be managed
and installed by using `pip` in a configured virtual environment, or `venv`.

Using direct instantiation is as simple as running the [main.py](../main.py)
file in the managed environment (by either using `uv run main.py` if using `uv`
or by running `python main.py` in the `venv` if using any other PEP-518
compliant tool).

## Docker file 

The usage of the docker file is simpler than the direct instantiation, as the
image only needs to be built (or use the pre-built image in
`atnog-harbor.av.it.pt/dt4mob/texture-creation`).


## Helm Chart

The helm chart is available at the [dt4mob-platform GitHub
repository](https://github.com/ATNoG/dt4mob-platform) and can be installed
using the Helm installer (`helm install texture-creation <path_to_chart> -f <path_to_values.yml>`)
The configuration is also done by using the respective environment variables in `values.yml`
