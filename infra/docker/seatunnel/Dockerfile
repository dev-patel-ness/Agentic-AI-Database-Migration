# Custom SeaTunnel image for the Data Agent: apache/seatunnel's Zeta engine,
# local execution mode, with just the JDBC connector installed (our only use
# case is JDBC -> JDBC bulk load between Oracle/MySQL/PostgreSQL) plus the 3
# vendor JDBC driver jars.
#
# Build: docker compose build seatunnel   (run infra/docker/seatunnel/fetch_jdbc_drivers.ps1 first)
ARG SEATUNNEL_VERSION=2.3.9
FROM apache/seatunnel:${SEATUNNEL_VERSION}

# NOTE: bin/install-plugin.sh in this image shells out to a `mvnw` wrapper
# that doesn't exist in the published Docker image (only in the source
# distribution) -- fetch_jdbc_drivers.ps1 downloads connector-jdbc directly
# from Maven Central into ./connectors instead of relying on that script.
COPY connectors/*.jar /opt/seatunnel/connectors/

# Vendor JDBC driver jars (Oracle ojdbc11, MySQL Connector/J, PostgreSQL JDBC)
# -- fetched by fetch_jdbc_drivers.ps1 into ./jars/ (gitignored: redistribution
# terms vary per vendor). The base image already bundles older driver jars
# for the same classes (postgresql-42.4.3.jar, ojdbc8-*.jar) -- remove them
# first so there's no ambiguity over which version's class the JVM loads.
RUN rm -f /opt/seatunnel/lib/postgresql-42.4.3.jar /opt/seatunnel/lib/ojdbc8-*.jar
COPY jars/*.jar /opt/seatunnel/lib/

WORKDIR /opt/seatunnel
