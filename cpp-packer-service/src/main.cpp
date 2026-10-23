// main.cpp - PackWise C++ packing HTTP microservice.
//
// Endpoints (all JSON, all dimensions are integer millimetres):
//   GET  /health            -> service status and algorithm capabilities
//   POST /v1/pack/cartons   -> evaluate items against one or more fixed cartons
//   POST /v1/pack/design    -> original behaviour: design a bounding box
//
// Configuration:
//   PACKER_HOST (default 127.0.0.1), PACKER_PORT (default 8090)
//   or command line: packer_service [port] [host]
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <set>
#include <string>

#include "httplib.h"
#include "nlohmann/json.hpp"
#include "packer_core.hpp"

using json = nlohmann::json;
using namespace std;

namespace {

const char* kVersion = "1.1.0";
const long long kMaxDim = 100000;  // 100 m, in mm
const size_t kMaxItems = 10000;    // same limit as the original main()
const size_t kMaxCartons = 100;

struct BadRequest {
    string code;
    string message;
};

json capabilities() {
    return {
        {"algorithm", "row/shelf heuristic from original packer.cpp"},
        {"layers", "single"},
        {"stacking", false},
        {"tipping_items", false},
        {"floor_rotation_90deg", true},
        {"weight_aware", false},
        {"padding_aware", false},
        {"units", "mm"},
        {"modes", {"cartons", "design", "sweep"}}};
}

void sendError(httplib::Response& res, int status, const string& code,
               const string& message) {
    res.status = status;
    res.set_content(json{{"error", {{"code", code}, {"message", message}}}}.dump(),
                    "application/json");
}

long long readDim(const json& obj, const char* key, const string& where) {
    if (!obj.contains(key)) throw BadRequest{"missing_field", where + " is missing '" + key + "'"};
    const json& v = obj.at(key);
    if (!v.is_number_integer())
        throw BadRequest{"invalid_dimension",
                         where + "." + key + " must be an integer number of millimetres"};
    const long long d = v.get<long long>();
    if (d <= 0 || d > kMaxDim)
        throw BadRequest{"invalid_dimension",
                         where + "." + key + " must be between 1 and " + to_string(kMaxDim) + " mm"};
    return d;
}

string readId(const json& obj, const string& where) {
    if (!obj.contains("id") || !obj.at("id").is_string())
        throw BadRequest{"invalid_id", where + ".id must be a string"};
    string id = obj.at("id").get<string>();
    if (id.empty() || id.size() > 64)
        throw BadRequest{"invalid_id", where + ".id must be 1-64 characters"};
    return id;
}

// Parses items into algorithm Items (ids 0..n-1) and keeps the external ids.
vector<packer::Item> parseItems(const json& body, vector<string>& externalIds) {
    if (!body.contains("items") || !body.at("items").is_array())
        throw BadRequest{"invalid_items", "'items' must be an array"};
    const json& arr = body.at("items");
    if (arr.empty() || arr.size() > kMaxItems)
        throw BadRequest{"invalid_items", "'items' must contain 1 to " + to_string(kMaxItems) + " entries"};

    vector<packer::Item> items;
    set<string> seen;
    for (size_t i = 0; i < arr.size(); ++i) {
        const string where = "items[" + to_string(i) + "]";
        if (!arr[i].is_object()) throw BadRequest{"invalid_items", where + " must be an object"};
        string id = readId(arr[i], where);
        if (!seen.insert(id).second) throw BadRequest{"duplicate_id", "Duplicate item id '" + id + "'"};
        packer::Item it{readDim(arr[i], "l", where), readDim(arr[i], "w", where),
                        readDim(arr[i], "h", where), static_cast<int>(i)};
        items.push_back(it);
        externalIds.push_back(id);
    }
    return items;
}

json placementsInCartonFrame(const packer::CartonFit& fit, const vector<string>& ids) {
    const auto& attempt = fit.attempts[fit.chosen];
    const bool swapAxes = attempt.orientation == "rows_along_width";
    json out = json::array();
    int seq = 1;
    for (int id : fit.sequence) {
        const auto& p = attempt.result.p[id];
        // Carton frame: x runs along the carton length, y along its width.
        const long long x = swapAxes ? p.y : p.x;
        const long long y = swapAxes ? p.x : p.y;
        const long long dx = swapAxes ? p.w : p.l;
        const long long dy = swapAxes ? p.l : p.w;
        out.push_back({{"id", ids[id]}, {"seq", seq++}, {"x", x}, {"y", y}, {"z", p.z},
                       {"dx", dx}, {"dy", dy}, {"dz", p.h}, {"rotated", p.rotated}});
    }
    return out;
}

void handleCartons(const httplib::Request& req, httplib::Response& res) {
    const auto t0 = chrono::steady_clock::now();
    json body;
    try {
        body = json::parse(req.body);
    } catch (const json::parse_error& e) {
        return sendError(res, 400, "malformed_json", string("Request body is not valid JSON: ") + e.what());
    }
    try {
        if (!body.is_object()) throw BadRequest{"malformed_json", "Request body must be a JSON object"};
        vector<string> ids;
        vector<packer::Item> items = parseItems(body, ids);

        if (!body.contains("cartons") || !body.at("cartons").is_array())
            throw BadRequest{"invalid_cartons", "'cartons' must be an array"};
        const json& cartons = body.at("cartons");
        if (cartons.empty() || cartons.size() > kMaxCartons)
            throw BadRequest{"invalid_cartons", "'cartons' must contain 1 to " + to_string(kMaxCartons) + " entries"};

        json results = json::array();
        for (size_t c = 0; c < cartons.size(); ++c) {
            const string where = "cartons[" + to_string(c) + "]";
            if (!cartons[c].is_object()) throw BadRequest{"invalid_cartons", where + " must be an object"};
            const string cid = readId(cartons[c], where);
            const long long L = readDim(cartons[c], "l", where);
            const long long W = readDim(cartons[c], "w", where);
            const long long H = readDim(cartons[c], "h", where);

            packer::CartonFit fit = packer::fitCarton(items, L, W, H);

            json attempts = json::array();
            for (const auto& a : fit.attempts) {
                json aj{{"orientation", a.orientation}, {"target_width", a.targetWidth},
                        {"row_limit", a.rowLimit}, {"fits", a.fits},
                        {"widths_tried", a.widthsTried}, {"widths_that_fit", a.widthsThatFit}};
                if (a.fits) aj["best_width"] = a.bestWidth;
                if (!a.fits) aj["reason"] = a.reason;
                if (std::isfinite(static_cast<double>(a.result.score)))
                    aj["used"] = {{"row_width", a.result.W}, {"rows_depth", a.result.L},
                                  {"height", a.result.H}};
                attempts.push_back(aj);
            }

            json r{{"carton_id", cid}, {"carton", {{"l", L}, {"w", W}, {"h", H}}},
                   {"fits", fit.fits}, {"attempts", attempts}};
            if (fit.fits) {
                const auto& a = fit.attempts[fit.chosen];
                const bool swapAxes = a.orientation == "rows_along_width";
                r["orientation"] = a.orientation;
                r["used"] = {{"x", swapAxes ? a.result.L : a.result.W},
                             {"y", swapAxes ? a.result.W : a.result.L},
                             {"z", a.result.H}};
                r["placements"] = placementsInCartonFrame(fit, ids);
            }
            results.push_back(r);
        }

        const double ms = chrono::duration<double, milli>(chrono::steady_clock::now() - t0).count();
        res.set_content(json{{"engine", {{"name", "packwise-packer"}, {"version", kVersion}}},
                             {"mode", "cartons"},
                             {"frame", "x along carton length, y along carton width, z up; mm"},
                             {"item_count", items.size()},
                             {"elapsed_ms", ms},
                             {"results", results}}.dump(),
                        "application/json");
    } catch (const BadRequest& e) {
        sendError(res, 400, e.code, e.message);
    } catch (const exception& e) {
        sendError(res, 500, "internal_error", e.what());
    }
}

void handleDesign(const httplib::Request& req, httplib::Response& res) {
    json body;
    try {
        body = json::parse(req.body);
    } catch (const json::parse_error& e) {
        return sendError(res, 400, "malformed_json", string("Request body is not valid JSON: ") + e.what());
    }
    try {
        if (!body.is_object()) throw BadRequest{"malformed_json", "Request body must be a JSON object"};
        vector<string> ids;
        vector<packer::Item> items = parseItems(body, ids);
        packer::Result best = packer::design(items);
        if (best.p.empty() || !std::isfinite(static_cast<double>(best.score)))
            return sendError(res, 422, "no_solution", "The algorithm did not find a placement");

        json placements = json::array();
        for (size_t i = 0; i < items.size(); ++i) {
            const auto& p = best.p[i];
            placements.push_back({{"id", ids[i]}, {"x", p.x}, {"y", p.y}, {"z", p.z},
                                  {"l", p.l}, {"w", p.w}, {"h", p.h}, {"rotated", p.rotated}});
        }
        res.set_content(json{{"engine", {{"name", "packwise-packer"}, {"version", kVersion}}},
                             {"mode", "design"},
                             {"box", {{"W", best.W}, {"L", best.L}, {"H", best.H}}},
                             {"score", static_cast<double>(best.score)},
                             {"placements", placements}}.dump(),
                        "application/json");
    } catch (const BadRequest& e) {
        sendError(res, 400, e.code, e.message);
    } catch (const exception& e) {
        sendError(res, 500, "internal_error", e.what());
    }
}

void handleSweep(const httplib::Request& req, httplib::Response& res) {
    json body;
    try {
        body = json::parse(req.body);
    } catch (const json::parse_error& e) {
        return sendError(res, 400, "malformed_json", string("Request body is not valid JSON: ") + e.what());
    }
    try {
        if (!body.is_object()) throw BadRequest{"malformed_json", "Request body must be a JSON object"};
        vector<string> ids;
        vector<packer::Item> items = parseItems(body, ids);
        packer::Trace t = packer::designTrace(items);
        if (t.best < 0)
            return sendError(res, 422, "no_solution", "The algorithm did not find a placement");

        json trials = json::array();
        for (const auto& tr : t.trials) {
            json j{{"k", tr.k}, {"width", tr.width}, {"fits", tr.fits}};
            if (tr.fits) {
                j["W"] = tr.result.W; j["L"] = tr.result.L; j["H"] = tr.result.H;
                j["volume"] = tr.result.W * tr.result.L * tr.result.H;
                j["score"] = static_cast<double>(tr.result.score);
            }
            trials.push_back(j);
        }
        const auto& best = t.trials[t.best].result;
        json order = json::array();
        for (int id : t.order) order.push_back(ids[id]);
        json placements = json::array();
        int seq = 1;
        for (int id : t.order) {
            const auto& p = best.p[id];
            placements.push_back({{"id", ids[id]}, {"seq", seq++}, {"x", p.x}, {"y", p.y}, {"z", p.z},
                                  {"l", p.l}, {"w", p.w}, {"h", p.h}, {"rotated", p.rotated}});
        }
        res.set_content(json{{"engine", {{"name", "packwise-packer"}, {"version", kVersion}}},
                             {"mode", "sweep"},
                             {"lo", t.lo}, {"hi", t.hi}, {"trial_count", t.trials.size()},
                             {"best", t.best}, {"best_width", t.trials[t.best].width},
                             {"box", {{"W", best.W}, {"L", best.L}, {"H", best.H}}},
                             {"score", static_cast<double>(best.score)},
                             {"order", order}, {"placements", placements}, {"trials", trials}}.dump(),
                        "application/json");
    } catch (const BadRequest& e) {
        sendError(res, 400, e.code, e.message);
    } catch (const exception& e) {
        sendError(res, 500, "internal_error", e.what());
    }
}

}  // namespace

int main(int argc, char** argv) {
    string host = getenv("PACKER_HOST") ? getenv("PACKER_HOST") : "127.0.0.1";
    int port = getenv("PACKER_PORT") ? atoi(getenv("PACKER_PORT")) : 8090;
    if (argc > 1) port = atoi(argv[1]);
    if (argc > 2) host = argv[2];
    if (port <= 0 || port > 65535) {
        cerr << "Invalid port\n";
        return 1;
    }

    httplib::Server svr;
    svr.set_payload_max_length(4 * 1024 * 1024);

    svr.Get("/health", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(json{{"status", "ok"}, {"service", "packwise-packer"},
                             {"version", kVersion}, {"capabilities", capabilities()}}.dump(),
                        "application/json");
    });
    svr.Post("/v1/pack/cartons", handleCartons);
    svr.Post("/v1/pack/design", handleDesign);
    svr.Post("/v1/pack/sweep", handleSweep);

    svr.set_error_handler([](const httplib::Request&, httplib::Response& res) {
        if (res.body.empty()) {
            const string code = res.status == 404 ? "not_found" : "http_error";
            res.set_content(json{{"error", {{"code", code}, {"message", "HTTP " + to_string(res.status)}}}}.dump(),
                            "application/json");
        }
    });
    svr.set_logger([](const httplib::Request& req, const httplib::Response& res) {
        cout << req.method << " " << req.path << " -> " << res.status << endl;
    });

    cout << "PackWise packer service listening on http://" << host << ":" << port << endl;
    if (!svr.listen(host, port)) {
        cerr << "Could not bind to " << host << ":" << port << " (is the port in use?)\n";
        return 1;
    }
    return 0;
}
