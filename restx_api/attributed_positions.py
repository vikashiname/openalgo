import os

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from limiter import limiter
from services.attributed_positions_service import get_attributed_positions
from utils.logging import get_logger

from .account_schema import AttributedPositionsSchema

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10 per second")
api = Namespace("attributed_positions", description="Strategy Attributed Positions API")

# Initialize logger
logger = get_logger(__name__)

# Initialize schema
attributed_positions_schema = AttributedPositionsSchema()


@api.route("/", strict_slashes=False)
class AttributedPositions(Resource):
    @limiter.limit(API_RATE_LIMIT)
    def post(self):
        """Get strategy-attributed position book reconciled with broker net positions"""
        try:
            # Validate request data
            req_data = request.get_json(silent=True) or {}
            validated_data = attributed_positions_schema.load(req_data)

            api_key = validated_data["apikey"]
            strategy = validated_data.get("strategy")
            include_zero_residual = validated_data.get("include_zero_residual", False)

            # Call service
            success, response_data, status_code = get_attributed_positions(
                api_key=api_key,
                strategy=strategy,
                include_zero_residual=include_zero_residual,
            )

            return make_response(jsonify(response_data), status_code)

        except ValidationError as err:
            return make_response(jsonify({"status": "error", "message": err.messages}), 400)
        except Exception as e:
            logger.exception(f"Unexpected error in attributed positions endpoint: {e}")
            return make_response(
                jsonify({"status": "error", "message": "An unexpected error occurred"}), 500
            )
