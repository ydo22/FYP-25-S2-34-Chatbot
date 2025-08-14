<?php
require_once dirname(__DIR__) . '/db_connect.php';

class Furniture
{
    public ?int    $furnitureID   = null;
    public string  $name          = '';
    public string  $category      = '';
    public string $tags           = '';
    public string  $description   = '';
    public float   $price         = 0.0;
    public int     $stock_quantity= 0;
    public string  $image_url     = '';

    public function __construct(array $data = [])
    {
        foreach ($data as $key => $value) {
        if (property_exists($this, $key)) {
            $this->$key = $value;
            continue;
        }

        $camel = lcfirst(str_replace('_', '', ucwords($key, '_')));
        if (property_exists($this, $camel)) {
            $this->$camel = $value;
        }
    }
    }

    public static function count(string $searchTerm = ''): int
    {
        global $conn;

        $baseSql = "SELECT COUNT(*) AS total FROM furnitures";
        $params  = [];
        $types   = '';

        if (trim($searchTerm) !== '') {
            $decoded = urldecode($searchTerm);
            $decoded = str_replace('+', ' ', $decoded);
            $decoded = mb_strtolower(trim($decoded));

            $terms = preg_split('/[^\p{L}\p{N}]+/u', $decoded, -1, PREG_SPLIT_NO_EMPTY);

            $clauses = [];
            foreach ($terms as $t) {
                $like = '%' . $t . '%';
                $clauses[] = "(LOWER(name) LIKE ? OR LOWER(category) LIKE ? OR LOWER(REPLACE(COALESCE(tags,''), ',', ' ')) LIKE ?)";
                $params[]  = $like;
                $params[]  = $like;
                $params[]  = $like;
                $types    .= 'sss';
            }

            $where = implode(' AND ', $clauses);
            $sql   = "$baseSql WHERE $where";
        } else {
            $sql = $baseSql;
        }

        $stmt = mysqli_prepare($conn, $sql);
        if (!$stmt) {
            return 0;
        }
        if (!empty($params)) {
            mysqli_stmt_bind_param($stmt, $types, ...$params);
        }
        mysqli_stmt_execute($stmt);
        $result = mysqli_stmt_get_result($stmt);
        $row = mysqli_fetch_assoc($result);
        return (int) ($row['total'] ?? 0);
    }

    public static function findPaginated(int $offset, int $limit, string $searchTerm = ''): array
    {
        global $conn;

        $furnitures = [];
        $baseSql    = "SELECT * FROM furnitures";
        $params     = [];
        $types      = '';

        if (trim($searchTerm) !== '') {
            $decoded = urldecode($searchTerm);
            $decoded = str_replace('+', ' ', $decoded);
            $decoded = mb_strtolower(trim($decoded));

            $terms = preg_split('/[^\p{L}\p{N}]+/u', $decoded, -1, PREG_SPLIT_NO_EMPTY);

            $clauses = [];
            foreach ($terms as $t) {
                $like = '%' . $t . '%';
                $clauses[] = "(LOWER(name) LIKE ? OR LOWER(category) LIKE ? OR LOWER(REPLACE(COALESCE(tags,''), ',', ' ')) LIKE ?)";
                $params[]  = $like;
                $params[]  = $like;
                $params[]  = $like;
                $types    .= 'sss';
            }

            $where = implode(' AND ', $clauses);
            $sql   = "$baseSql WHERE $where ORDER BY furnitureID DESC LIMIT ?, ?";
        } else {
            $sql   = "$baseSql ORDER BY furnitureID DESC LIMIT ?, ?";
        }

        $params[] = $offset;
        $params[] = $limit;
        $types   .= 'ii';

        $stmt = mysqli_prepare($conn, $sql);
        if (!$stmt) {
            return $furnitures;
        }
        mysqli_stmt_bind_param($stmt, $types, ...$params);
        mysqli_stmt_execute($stmt);
        $result = mysqli_stmt_get_result($stmt);

        while ($row = mysqli_fetch_assoc($result)) {
            $furnitures[] = new self($row);
        }
        return $furnitures;
    }

    public static function findById(int $id): ?self
    {
        global $conn;
        $sql  = "SELECT * FROM furnitures WHERE furnitureID = ?";
        $stmt = mysqli_prepare($conn, $sql);
        mysqli_stmt_bind_param($stmt, 'i', $id);
        mysqli_stmt_execute($stmt);
        $result = mysqli_stmt_get_result($stmt);

        $row = mysqli_fetch_assoc($result);
        return $row ? new self($row) : null;
    }

    public function save(): bool
    {
        global $conn;

        if (empty($this->image_url)) {
            throw new RuntimeException('Image path cannot be empty');
        }

        if ($this->furnitureID) {
            $sql = "UPDATE furnitures
                    SET name            = ?,
                        category        = ?,
                        price           = ?,
                        stock_quantity  = ?,
                        description     = ?,
                        image_url       = ?
                    WHERE furnitureID   = ?";
            $stmt = mysqli_prepare($conn, $sql);
            mysqli_stmt_bind_param(
                $stmt,
                'ssdissi',
                $this->name,
                $this->category,
                $this->price,
                $this->stock_quantity,
                $this->description,
                $this->image_url,
                $this->furnitureID
            );
        } else {
            $sql = "INSERT INTO furnitures
                       (name, category, price, stock_quantity, description, image_url)
                    VALUES (?,?,?,?,?,?)";
            $stmt = mysqli_prepare($conn, $sql);
            mysqli_stmt_bind_param(
                $stmt,
                'ssdiss',
                $this->name,
                $this->category,
                $this->price,
                $this->stock_quantity,
                $this->description,
                $this->image_url
            );
        }

        $ok = mysqli_stmt_execute($stmt);
        if (!$this->furnitureID) {
            $this->furnitureID = mysqli_insert_id($conn);   
        }
        mysqli_stmt_close($stmt);
        return $ok;
    }

    public function delete(): bool
    {
        if (!$this->furnitureID) {
            error_log("Delete failed: furnitureID is null");
            throw new RuntimeException('Cannot delete unsaved Furniture');
        }

        global $conn;
        $sql  = "DELETE FROM furnitures WHERE furnitureID = ?";
        $stmt = mysqli_prepare($conn, $sql);
        mysqli_stmt_bind_param($stmt, 'i', $this->furnitureID);
        $ok = mysqli_stmt_execute($stmt);

        if (!$ok) {
            error_log("MySQL error: " . mysqli_error($conn));
        }

        mysqli_stmt_close($stmt);
        return $ok;
    }

}
